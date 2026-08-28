import os
import json
import time
from typing import Any, Dict, List, Optional

from src.execution.base import BaseExecutor
from src.health.http_check import HTTPHealthCheck
from src.health.wp_check import WPHealthCheck
from src.wp.cli import WPCLI
from src.logging.logger import logger

import uuid

class HealthCheckManager:
    def __init__(self, site_config: Dict[str, Any], executor: Optional[BaseExecutor] = None, wp_cli: Optional[WPCLI] = None):
        self.site_config = site_config
        self.executor = executor
        self.wp_cli = wp_cli
        self.site_name = site_config["site_name"]
        
        verify_ssl = site_config.get("ssl_verify", False)
        self.http_check = HTTPHealthCheck(site_config["health_check_url"], verify_ssl=verify_ssl)
        self.wp_check = WPHealthCheck(wp_cli) if wp_cli else None
        
        # Calculate log file path
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(src_dir)
        self.health_log_dir = os.path.join(project_root, "logs", "health")
        self.log_file = os.path.join(self.health_log_dir, f"{self.site_name}.jsonl")
        self.screenshots_dir = os.path.join(project_root, "screenshots")

    def run_all_checks(self, baseline_check_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Run HTTP and WP health checks, aggregate them, and log the result to a JSONL file.
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        import datetime
        check_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
        
        # 1. Run HTTP/Browser check
        browser_res = self.http_check.run_browser_check(self.site_name, check_id, self.screenshots_dir)

        # 2. Merge per-site acknowledgments into the error list
        acknowledged_errors = self._load_acknowledged_errors()
        browser_res["console_errors"] = self._apply_acknowledgments(
            browser_res.get("console_errors", []), acknowledged_errors
        )

        # 3. Re-evaluate browser check status after acknowledgment merge
        active_errors = [
            e for e in browser_res["console_errors"] if e.get("severity") != "ignored"
        ]
        has_asset_issues = bool(browser_res.get("broken_images")) or bool(browser_res.get("failed_asset_requests"))
        if browser_res["status_code"] > 302 or browser_res["status_code"] == 0 or active_errors or has_asset_issues:
            browser_res["status"] = "fail"
        else:
            browser_res["status"] = "pass"
        
        # 4. Run WP checks if config is Ready
        wp_res = None
        if self.wp_check:
            wp_res = self.wp_check.run_full_check()

        # 5. Load baseline check and perform comparison if baseline is provided
        baseline_report = None
        if baseline_check_id:
            baseline_report = self.get_health_check_by_id(baseline_check_id)

        console_errors_matched = True
        if baseline_report:
            pre_http = baseline_report.get("checks", {}).get("http", {})
            pre_errors = pre_http.get("console_errors", [])
            post_errors = browser_res.get("console_errors", [])
            # Only compare active (non-ignored) errors for baseline matching
            pre_active = [e for e in pre_errors if e.get("severity") != "ignored"]
            post_active = [e for e in post_errors if e.get("severity") != "ignored"]
            console_errors_matched = self._compare_console_errors(pre_active, post_active)

        asset_issues_matched = True
        if baseline_report:
            pre_http = baseline_report.get("checks", {}).get("http", {})
            asset_issues_matched = (
                self._compare_asset_issues(pre_http.get("broken_images", []), browser_res.get("broken_images", []), key="src") and
                self._compare_asset_issues(pre_http.get("failed_asset_requests", []), browser_res.get("failed_asset_requests", []), key="url")
            )

        screenshot_diffs = {
            "matched": True,
            "desktop_diff": None,
            "mobile_diff": None
        }
        if baseline_report:
            pre_http = baseline_report.get("checks", {}).get("http", {})
            pre_screenshots = pre_http.get("screenshots")
            post_screenshots = browser_res.get("screenshots")
            if pre_screenshots and post_screenshots:
                screenshot_diffs = self._diff_screenshots(pre_screenshots, post_screenshots, check_id)

        # Load accepted visual diffs for this site
        accepted_diffs = self._load_accepted_visual_diffs()
        diff_accepted = any(d.get("check_id") == check_id for d in accepted_diffs)
        if screenshot_diffs:
            screenshot_diffs["accepted"] = diff_accepted

        # Determine overall status on a proportionate scale:
        # CRITICAL: Site down (status code >= 400 or 0) OR Database connection failure
        # DEGRADED: Response time > 5000ms, WP status degraded, or unaccepted screenshot diff unmatched
        # NOTICE: Site up (200 OK), DB connected, but browser emitted unacknowledged console errors
        # HEALTHY WITH EXCEPTION: Site up, DB connected, but has accepted visual diffs or acknowledged errors
        # HEALTHY: Site up (200 OK), DB connected, no errors
        overall_status = "healthy"
        status_reasons = []

        # Check for Critical outages first
        if browser_res["status_code"] >= 400:
            overall_status = "critical"
            status_reasons.append(f"HTTP response status error: {browser_res['status_code']}")
        elif browser_res["status_code"] == 0:
            overall_status = "critical"
            status_reasons.append(f"Site unreachable: {browser_res.get('error', 'Connection failed')}")
        elif self.wp_check and wp_res and wp_res.get("database_connection") == "fail":
            overall_status = "critical"
            status_reasons.append("WordPress database connection failure")
        
        # Check for Degraded performance / layout shifts
        if overall_status != "critical":
            if browser_res.get("response_time_ms", 0) > 5000:
                overall_status = "degraded"
                status_reasons.append(f"Slow response time: {browser_res['response_time_ms']} ms (threshold > 5000 ms)")
            if self.wp_check and wp_res and wp_res.get("status") == "degraded":
                overall_status = "degraded"
                status_reasons.append("WordPress core/plugin health checks degraded")
            if baseline_report and not screenshot_diffs.get("matched", True) and not diff_accepted:
                overall_status = "degraded"
                status_reasons.append("Visual layout differences detected between pre and post update")
            if has_asset_issues:
                overall_status = "degraded"
                broken_count = len(browser_res.get("broken_images", []))
                failed_count = len(browser_res.get("failed_asset_requests", []))
                status_reasons.append(f"{broken_count} broken image(s) and {failed_count} failed asset request(s) detected on the live page")

        # Check for Notice / Console errors on a functional page
        if overall_status not in ["critical", "degraded"]:
            if (browser_res.get("console_errors") and any(e.get("severity") != "ignored" for e in browser_res.get("console_errors", []))) or (baseline_report and not console_errors_matched):
                overall_status = "notice"
                status_reasons.append("Browser console emitted active JavaScript errors")
            elif diff_accepted or any(e.get("suppression_source") == "acknowledged" for e in browser_res.get("console_errors", [])):
                overall_status = "healthy with exception"
                if diff_accepted:
                    status_reasons.append("Visual layout difference accepted by admin")
                if any(e.get("suppression_source") == "acknowledged" for e in browser_res.get("console_errors", [])):
                    status_reasons.append("Console errors acknowledged by admin")

        if not status_reasons:
            status_reasons.append("All health checks passed cleanly")
            
        # Get core version
        core_version = "Unknown"
        if self.wp_check and wp_res and wp_res["database_connection"] == "pass":
            try:
                core_version = self.wp_cli.get_core_version()
            except Exception as e:
                logger.warning(f"Could not determine WP core version for '{self.site_name}': {e}. "
                                f"Reporting core version as 'Unknown' in this health check.")
                
        # Build aggregated error severity summary
        all_errors = browser_res.get("console_errors", [])
        error_summary = {
            "critical": sum(1 for e in all_errors if e.get("severity") == "critical"),
            "warning": sum(1 for e in all_errors if e.get("severity") == "warning"),
            "ignored": sum(1 for e in all_errors if e.get("severity") == "ignored"),
        }

        # Build aggregated report
        report = {
            "id": check_id,
            "timestamp": timestamp,
            "site_name": self.site_name,
            "overall_status": overall_status,
            "status_reasons": status_reasons,
            "checks": {
                "http": {
                    "status_code": browser_res["status_code"],
                    "response_time_ms": browser_res["response_time_ms"],
                    "status": browser_res["status"],
                    "console_errors": browser_res["console_errors"],
                    "error_summary": error_summary,
                    "screenshots": browser_res.get("screenshots"),
                    "console_errors_matched": console_errors_matched,
                    "screenshot_diffs": screenshot_diffs,
                    "broken_images": browser_res.get("broken_images", []),
                    "failed_asset_requests": browser_res.get("failed_asset_requests", []),
                    "asset_issues_matched": asset_issues_matched,
                },
                "wp_core": {
                    "version": core_version,
                    "status": wp_res["core_status"]["status"]
                } if self.wp_check and wp_res else None,
                "plugins": {
                    "active_count": wp_res["plugins"].get("active_count", 0),
                    "updates_available": wp_res["plugins"].get("updates_available", 0),
                    "status": wp_res["plugins"].get("status", "fail")
                } if self.wp_check and wp_res else None,
                "database": {
                    "connection": "ok" if wp_res["database_connection"] == "pass" else "failed",
                    "status": wp_res["database_connection"]
                } if self.wp_check and wp_res else None
            }
        }
        
        # Cache the latest snapshot first — this is what the homepage polls
        try:
            os.makedirs(self.health_log_dir, exist_ok=True)
            latest_path = os.path.join(self.health_log_dir, f"last_snapshot_{self.site_name}.json")
            with open(latest_path, "w", encoding="utf-8") as f_latest:
                json.dump(report, f_latest, indent=2)
        except Exception as snapshot_err:
            # Cache write failed; snapshot unavailable for future reads. JSONL history still captures the result.
            import logging
            logging.getLogger("app").warning(
                f"Failed to write latest snapshot for site '{self.site_name}': {snapshot_err}"
            )

        # Append to JSONL history log
        try:
            os.makedirs(self.health_log_dir, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(report) + "\n")
        except Exception as log_err:
            import logging
            logging.getLogger("app").warning(
                f"Failed to write health JSONL log for site '{self.site_name}': {log_err}"
            )
            
        return report

    def check_before_update(self) -> bool:
        """
        Run check before update. Returns True if healthy, healthy with exception, notice, or degraded, False if critical.
        """
        report = self.run_all_checks()
        return report["overall_status"] in ["healthy", "healthy with exception", "notice", "degraded"]

    def check_after_update(self) -> bool:
        """
        Run check after update. Returns True if healthy, healthy with exception, notice, or degraded, False if critical.
        """
        report = self.run_all_checks()
        return report["overall_status"] in ["healthy", "healthy with exception", "notice", "degraded"]

    def _load_accepted_visual_diffs(self) -> List[Dict[str, Any]]:
        """Load the list of accepted visual diffs for this site from admin_data.json."""
        try:
            from src.config.loader import SiteConfigManager
            admin_data = SiteConfigManager.load_admin_data()
            diffs = admin_data.get("accepted_visual_diffs", {}).get(self.site_name, [])
            return diffs if isinstance(diffs, list) else []
        except Exception as e:
            logger.warning(f"Could not load accepted visual diffs for '{self.site_name}': {e}. "
                            f"Previously-accepted diffs will appear unaccepted until this resolves.")
            return []

    def get_health_history(self, site_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve health check history from JSONL file, merged with the latest snapshot.

        The latest snapshot is prepended to the history if it is newer than the most recent
        JSONL entry, so the UI always reflects the current state even when a JSONL write failed.
        """
        if site_name is None or site_name == self.site_name:
            log_file = self.log_file
            snapshot_site = self.site_name
        else:
            src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_root = os.path.dirname(src_dir)
            log_file = os.path.join(project_root, "logs", "health", f"{site_name}.jsonl")
            snapshot_site = site_name

        history: List[Dict[str, Any]] = []
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            history.append(json.loads(line))
                        except Exception as e:
                            logger.warning(f"Skipping corrupted health history line in '{log_file}': {e}")

        # Sort descending by timestamp
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Merge latest snapshot if it's newer than the latest JSONL entry
        snapshot_path = os.path.join(self.health_log_dir, f"last_snapshot_{snapshot_site}.json")
        if os.path.exists(snapshot_path):
            try:
                with open(snapshot_path, "r", encoding="utf-8") as f_snap:
                    snapshot = json.load(f_snap)
                latest_ts = history[0].get("timestamp", "") if history else ""
                snapshot_ts = snapshot.get("timestamp", "")
                if snapshot_ts > latest_ts:
                    history.insert(0, snapshot)
            except Exception as e:
                logger.warning(f"Could not merge latest snapshot for '{snapshot_site}': {e}. "
                                f"History may not reflect the most recent check if the JSONL write also failed.")

        # Dynamically re-evaluate error & visual diff acknowledgments for history items
        acknowledged_errors = self._load_acknowledged_errors()
        accepted_diffs = self._load_accepted_visual_diffs()

        for check in history:
            cid = check.get("id")
            http = check.get("checks", {}).get("http", {})
            raw_errors = http.get("console_errors", [])
            diff_meta = http.get("screenshot_diffs", {})

            # 1. Check if visual diff was accepted
            is_accepted_diff = any(d.get("check_id") == cid for d in accepted_diffs)
            if diff_meta:
                diff_meta["accepted"] = is_accepted_diff

            # 2. Check console errors
            enriched = self._apply_acknowledgments(raw_errors, acknowledged_errors) if raw_errors else []
            if raw_errors:
                http["console_errors"] = enriched
                http["error_summary"] = {
                    "critical": sum(1 for e in enriched if e.get("severity") == "critical"),
                    "warning": sum(1 for e in enriched if e.get("severity") == "warning"),
                    "ignored": sum(1 for e in enriched if e.get("severity") == "ignored"),
                }

            # 3. Dynamic overall_status calculation
            active_errors = [e for e in enriched if e.get("severity") != "ignored"]
            unaccepted_diff = not diff_meta.get("matched", True) and not is_accepted_diff
            
            if http.get("status_code", 0) in [200, 301, 302] and not active_errors and not unaccepted_diff:
                if is_accepted_diff or any(e.get("suppression_source") == "acknowledged" for e in enriched):
                    check["overall_status"] = "healthy with exception"
                    reasons = []
                    if is_accepted_diff:
                        reasons.append("Visual layout difference accepted by admin")
                    if any(e.get("suppression_source") == "acknowledged" for e in enriched):
                        reasons.append("Console errors acknowledged by admin")
                    check["status_reasons"] = reasons

        return history


    def get_health_check_by_id(self, check_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific health check by its unique ID.
        """
        history = self.get_health_history()
        for check in history:
            if check.get("id") == check_id:
                return check
        return None

    def _load_acknowledged_errors(self) -> List[Dict[str, Any]]:
        """Load the list of operator-acknowledged errors for this site from admin_data.json.

        Returns:
            List of acknowledged error dicts (each has ``fingerprint`` and ``reason`` keys).
        """
        try:
            from src.config.loader import SiteConfigManager
            admin_data = SiteConfigManager.load_admin_data()
            acks = admin_data.get("acknowledged_errors", {}).get(self.site_name, [])
            return acks if isinstance(acks, list) else []
        except Exception as e:
            logger.warning(f"Could not load acknowledged errors for '{self.site_name}': {e}. "
                            f"Previously-acknowledged errors will appear unacknowledged until this resolves.")
            return []

    def _apply_acknowledgments(
        self, errors: List[Dict[str, Any]], acknowledged: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Override severity to ``'ignored'`` for errors whose fingerprint is acknowledged.

        Acknowledged errors are still surfaced in the report — they just no longer
        contribute to the overall health status.

        Args:
            errors: Enriched console error list from ``ConsoleErrorClassifier.enrich()``.
            acknowledged: Per-site acknowledgment list loaded from admin_data.json.

        Returns:
            Updated error list with severity overridden where applicable.
        """
        ack_fingerprints: Dict[str, Dict[str, Any]] = {
            ack["fingerprint"]: ack for ack in acknowledged if "fingerprint" in ack
        }
        updated = []
        for err in errors:
            fingerprint = err.get("fingerprint", "")
            if fingerprint in ack_fingerprints and err.get("severity") != "ignored":
                err = dict(err)
                err["severity"] = "ignored"
                err["suppression_source"] = "acknowledged"
                err["suppression_reason"] = ack_fingerprints[fingerprint].get(
                    "reason", "Acknowledged by operator"
                )
                err["acknowledged_at"] = ack_fingerprints[fingerprint].get("acknowledged_at")
            updated.append(err)
        return updated

    def _compare_console_errors(
        self, pre_errors: List[Dict[str, Any]], post_errors: List[Dict[str, Any]]
    ) -> bool:
        """
        Compare post-update console errors against the pre-update baseline.
        Returns True if all post-update errors were already present in pre-update (no new errors)
        and the count has not increased.
        """
        if len(post_errors) > len(pre_errors):
            return False
            
        pre_texts = {err.get("text", "") for err in pre_errors}
        for err in post_errors:
            if err.get("text", "") not in pre_texts:
                return False

        return True

    def _compare_asset_issues(
        self, pre_issues: List[Dict[str, Any]], post_issues: List[Dict[str, Any]], key: str
    ) -> bool:
        """
        Compare post-update broken images / failed asset requests against the
        pre-update baseline. Returns True if every post-update issue was already
        present pre-update (no new breakage) and the count has not increased —
        mirrors _compare_console_errors so an image that was already broken
        before the update doesn't trigger a rollback the update didn't cause.
        """
        if len(post_issues) > len(pre_issues):
            return False

        pre_keys = {issue.get(key, "") for issue in pre_issues}
        for issue in post_issues:
            if issue.get(key, "") not in pre_keys:
                return False

        return True

    def _diff_screenshots(self, pre_screenshots: Dict[str, Any], post_screenshots: Dict[str, Any], check_id: str) -> Dict[str, Any]:
        """
        Compare pre-update and post-update screenshots using Pillow.
        If there's any visual difference, save visual diff images.
        """
        from PIL import Image, ImageChops
        
        pre_year_month = pre_screenshots.get("year_month")
        post_year_month = post_screenshots.get("year_month")
        
        diff_res = {
            "matched": True,
            "desktop_diff": None,
            "mobile_diff": None
        }
        
        devices = ["desktop", "mobile"]
        for device in devices:
            pre_file = pre_screenshots.get(device)
            post_file = post_screenshots.get(device)
            if not pre_file or not post_file:
                continue
                
            pre_path = os.path.join(self.screenshots_dir, self.site_name, pre_year_month, pre_file)
            post_path = os.path.join(self.screenshots_dir, self.site_name, post_year_month, post_file)
            
            if not os.path.exists(pre_path) or not os.path.exists(post_path):
                diff_res["matched"] = False
                continue
                
            try:
                img_pre = Image.open(pre_path).convert("RGB")
                img_post = Image.open(post_path).convert("RGB")
                
                # Check if sizes match, resize if not
                if img_pre.size != img_post.size:
                    img_post = img_post.resize(img_pre.size)
                    
                diff = ImageChops.difference(img_pre, img_post)
                bbox = diff.getbbox()
                
                if bbox is not None:
                    # Images do not match
                    diff_res["matched"] = False
                    
                    # Generate visual diff image
                    diff_data = diff.load()
                    img_pre_data = img_pre.load()
                    
                    width, height = img_pre.size
                    highlighted = Image.new("RGB", (width, height))
                    h_data = highlighted.load()
                    
                    # Loop pixels and highlight differences
                    for y in range(height):
                        for x in range(width):
                            r_diff, g_diff, b_diff = diff_data[x, y]
                            if r_diff > 10 or g_diff > 10 or b_diff > 10:
                                h_data[x, y] = (255, 0, 128)  # Highlight in magenta
                            else:
                                r, g, b = img_pre_data[x, y]
                                h_data[x, y] = (int(r * 0.7), int(g * 0.7), int(b * 0.7))
                                
                    diff_filename = f"{check_id}_{device}_diff.png"
                    diff_path = os.path.join(self.screenshots_dir, self.site_name, post_year_month, diff_filename)
                    highlighted.save(diff_path)
                    
                    diff_res[f"{device}_diff"] = diff_filename
            except Exception as e:
                logger.warning(f"Error during screenshot diffing for '{self.site_name}': {e}")
                diff_res["matched"] = False
                
        return diff_res

