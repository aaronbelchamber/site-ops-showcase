import os
import json
from datetime import datetime, timezone
from flask import Blueprint, request
from src.config.loader import load_sites_config, load_credentials, SiteConfigManager
from src.execution import get_executor
from src.wp.cli import WPCLI
from src.health.manager import HealthCheckManager
from src.api.auth import require_api_key
from src.api.tasks import start_task, operation_in_progress_response, site_operation
from src.api.response import ok, err
from src.logging.logger import logger

health_bp = Blueprint("health", __name__)


class HealthTaskRunner:
    @staticmethod
    def run_health_check_task(site_name: str):
        sites = load_sites_config()
        site_config = sites[site_name]

        if site_config.get("status", "Ready") == "Ready":
            credentials = load_credentials()
            executor = get_executor(site_config, credentials)
            try:
                wp_cli = WPCLI(executor, site_config["wp_path"], site_config.get("wp_cli_path"))
                mgr = HealthCheckManager(site_config, executor, wp_cli)
                report = mgr.run_all_checks()
            finally:
                executor.disconnect()
        else:
            mgr = HealthCheckManager(site_config, executor=None, wp_cli=None)
            report = mgr.run_all_checks()

        logger.info(f"Health check executed for site '{site_name}'. Status: '{report.get('overall_status')}'.")
        return report


class HealthController:
    @staticmethod
    @require_api_key
    def check_health(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)

            is_async = request.args.get("async", "false").lower() == "true"
            if is_async:
                task_id = start_task(
                    f"Health check for {site_name}",
                    HealthTaskRunner.run_health_check_task,
                    site_name=site_name
                )
                if task_id is None:
                    return operation_in_progress_response(site_name)
                return ok({"task_id": task_id, "status": "running"})

            # The synchronous path does the same real work as the async one
            # (SSH + a headless browser), so it takes the same per-site lock.
            # Without it the dashboard could stack one live check per card on
            # the same site while a background task was already running.
            with site_operation(site_name) as acquired:
                if not acquired:
                    return operation_in_progress_response(site_name)
                report = HealthTaskRunner.run_health_check_task(site_name)
                return ok(report)
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def get_health_history(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
                
            site_config = sites[site_name]
            mgr = HealthCheckManager(site_config, executor=None, wp_cli=None)
            history = mgr.get_health_history()
            return ok(history)
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def get_health_check(site_name, check_id):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
            
            site_config = sites[site_name]
            mgr = HealthCheckManager(site_config, executor=None, wp_cli=None)
            check = mgr.get_health_check_by_id(check_id)
            if not check:
                return err(f"Health check '{check_id}' not found.", 404)
            
            return ok(check)
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def get_health_screenshot(site_name, check_id, device):
        if device not in ["desktop", "mobile", "desktop_diff", "mobile_diff"]:
            return err("Invalid device/diff type. Must be 'desktop', 'mobile', 'desktop_diff', or 'mobile_diff'.", 400)
        
        try:
            from flask import send_from_directory
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
            
            site_config = sites[site_name]
            mgr = HealthCheckManager(site_config, executor=None, wp_cli=None)
            check = mgr.get_health_check_by_id(check_id)
            if not check:
                return err(f"Health check '{check_id}' not found.", 404)
            
            screenshots_meta = check.get("checks", {}).get("http", {}).get("screenshots")
            if not screenshots_meta:
                return err("No screenshots found for this check.", 404)
            
            if device.endswith("_diff"):
                diffs_meta = check.get("checks", {}).get("http", {}).get("screenshot_diffs", {})
                filename = diffs_meta.get(device)
            else:
                filename = screenshots_meta.get(device)
                
            year_month = screenshots_meta.get("year_month")
            if not filename or not year_month:
                return err("Screenshot/diff metadata is incomplete.", 404)
            
            directory = os.path.join(mgr.screenshots_dir, site_name, year_month)
            return send_from_directory(directory, filename)
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def get_latest_snapshot(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
            
            site_config = sites[site_name]
            mgr = HealthCheckManager(site_config, executor=None, wp_cli=None)
            
            path = os.path.join(mgr.health_log_dir, f"last_snapshot_{site_name}.json")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    # Re-evaluate acknowledgments and visual diff acceptance on snapshot data
                    acks = mgr._load_acknowledged_errors()
                    accepted_diffs = mgr._load_accepted_visual_diffs()
                    cid = data.get("id")

                    http = data.get("checks", {}).get("http", {})
                    raw_errs = http.get("console_errors", [])
                    diff_meta = http.get("screenshot_diffs", {})

                    is_accepted_diff = any(d.get("check_id") == cid for d in accepted_diffs)
                    if diff_meta:
                        diff_meta["accepted"] = is_accepted_diff

                    enriched = mgr._apply_acknowledgments(raw_errs, acks) if raw_errs and acks else raw_errs
                    if enriched:
                        http["console_errors"] = enriched
                        http["error_summary"] = {
                            "critical": sum(1 for e in enriched if e.get("severity") == "critical"),
                            "warning": sum(1 for e in enriched if e.get("severity") == "warning"),
                            "ignored": sum(1 for e in enriched if e.get("severity") == "ignored"),
                        }

                    active_errs = [e for e in enriched if e.get("severity") != "ignored"]
                    unaccepted_diff = not diff_meta.get("matched", True) and not is_accepted_diff

                    if http.get("status_code", 0) in [200, 301, 302] and not active_errs and not unaccepted_diff:
                        if is_accepted_diff or any(e.get("suppression_source") == "acknowledged" for e in enriched):
                            data["overall_status"] = "healthy with exception"

                    return ok(data)
                except Exception:
                    # Failed to enrich health data; return None (snapshot unavailable)
                    pass

            return ok(None)
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def purge_health_data(site_name):
        """Purge health check history logs and screenshot files for the given site."""
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
            
            site_config = sites[site_name]
            mgr = HealthCheckManager(site_config, executor=None, wp_cli=None)
            
            # 1. Delete the health JSONL log file
            if os.path.exists(mgr.log_file):
                os.remove(mgr.log_file)
                
            # 2. Delete the latest cached snapshot
            latest_snapshot_path = os.path.join(mgr.health_log_dir, f"last_snapshot_{site_name}.json")
            if os.path.exists(latest_snapshot_path):
                os.remove(latest_snapshot_path)
                
            # 3. Delete the site's screenshots directory
            site_screenshots_directory = os.path.join(mgr.screenshots_dir, site_name)
            if os.path.exists(site_screenshots_directory):
                import shutil
                shutil.rmtree(site_screenshots_directory)
                
            return ok({
                    "message": f"Health history and screenshots purged for site '{site_name}'."
                })
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def get_acknowledged_errors(site_name: str):
        """List all operator-acknowledged console errors for a site."""
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)

            admin_data = SiteConfigManager.load_admin_data()
            acks = admin_data.get("acknowledged_errors", {}).get(site_name, [])
            return ok(acks)
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def acknowledge_error(site_name: str):
        """Acknowledge a console error fingerprint so it no longer blocks site health.

        Expects JSON body: { "fingerprint": str, "reason": str (optional) }
        """
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)

            body = request.get_json(force=True, silent=True) or {}
            fingerprint = (body.get("fingerprint") or "").strip()
            if not fingerprint:
                return err("'fingerprint' is required.", 400)

            reason = (body.get("reason") or "Acknowledged by operator").strip()

            admin_data = SiteConfigManager.load_admin_data()
            acks_root = admin_data.setdefault("acknowledged_errors", {})
            site_acks: list = acks_root.setdefault(site_name, [])

            # Prevent duplicate acknowledgments
            if any(ack.get("fingerprint") == fingerprint for ack in site_acks):
                return ok({"message": "Error already acknowledged."})

            site_acks.append({
                "fingerprint": fingerprint,
                "reason": reason,
                "acknowledged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            SiteConfigManager.save_admin_data(admin_data)
            logger.info(f"Console error '{fingerprint}' acknowledged for site '{site_name}'. Reason: {reason}")

            return ok({"message": f"Error '{fingerprint}' acknowledged for site '{site_name}'."})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def unacknowledge_error(site_name: str, fingerprint: str):
        """Remove a previously acknowledged console error, restoring its original severity."""
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)

            admin_data = SiteConfigManager.load_admin_data()
            acks_root = admin_data.get("acknowledged_errors", {})
            site_acks: list = acks_root.get(site_name, [])

            updated_acks = [ack for ack in site_acks if ack.get("fingerprint") != fingerprint]
            if len(updated_acks) == len(site_acks):
                return err(f"Acknowledgment '{fingerprint}' not found for site '{site_name}'.", 404)

            acks_root[site_name] = updated_acks
            admin_data["acknowledged_errors"] = acks_root
            SiteConfigManager.save_admin_data(admin_data)
            return ok({"message": f"Acknowledgment '{fingerprint}' removed for site '{site_name}'."})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def get_accepted_visual_diffs(site_name: str):
        """List all accepted visual diffs for a site."""
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)

            admin_data = SiteConfigManager.load_admin_data()
            diffs = admin_data.get("accepted_visual_diffs", {}).get(site_name, [])
            return ok(diffs)
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def accept_visual_diff(site_name: str):
        """Accept a visual diff for a check_id so it no longer blocks status or updates."""
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)

            body = request.get_json(force=True, silent=True) or {}
            check_id = (body.get("check_id") or "").strip()
            if not check_id:
                return err("'check_id' is required.", 400)

            reason = (body.get("reason") or "Accepted visual difference").strip()

            admin_data = SiteConfigManager.load_admin_data()
            diffs_root = admin_data.setdefault("accepted_visual_diffs", {})
            site_diffs: list = diffs_root.setdefault(site_name, [])

            if any(item.get("check_id") == check_id for item in site_diffs):
                return ok({"message": "Visual diff already accepted."})

            site_diffs.append({
                "check_id": check_id,
                "reason": reason,
                "accepted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            SiteConfigManager.save_admin_data(admin_data)
            logger.info(f"Visual diff for check '{check_id}' accepted for site '{site_name}'. Reason: {reason}")

            return ok({"message": f"Visual diff for check '{check_id}' accepted for site '{site_name}'."})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def unaccept_visual_diff(site_name: str, check_id: str):
        """Remove a previously accepted visual diff, re-rejecting it."""
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)

            admin_data = SiteConfigManager.load_admin_data()
            diffs_root = admin_data.get("accepted_visual_diffs", {})
            site_diffs: list = diffs_root.get(site_name, [])

            updated_diffs = [item for item in site_diffs if item.get("check_id") != check_id]
            if len(updated_diffs) == len(site_diffs):
                return err(f"Accepted visual diff '{check_id}' not found for site '{site_name}'.", 404)

            diffs_root[site_name] = updated_diffs
            admin_data["accepted_visual_diffs"] = diffs_root
            SiteConfigManager.save_admin_data(admin_data)
            logger.info(f"Visual diff acceptance for check '{check_id}' removed (re-rejected) for site '{site_name}'.")

            return ok({"message": f"Visual diff for check '{check_id}' re-rejected for site '{site_name}'."})
        except Exception as e:
            return err(str(e), 500)


# Route mappings to HealthController
health_bp.route("/<site_name>/health", methods=["GET"])(HealthController.check_health)
health_bp.route("/<site_name>/health/history", methods=["GET"])(HealthController.get_health_history)
health_bp.route("/<site_name>/health/latest", methods=["GET"])(HealthController.get_latest_snapshot)
health_bp.route("/<site_name>/health/<check_id>", methods=["GET"])(HealthController.get_health_check)
health_bp.route("/<site_name>/health/<check_id>/screenshot/<device>", methods=["GET"])(HealthController.get_health_screenshot)
health_bp.route("/<site_name>/health/purge", methods=["POST"])(HealthController.purge_health_data)
health_bp.route("/<site_name>/health/errors/acknowledged", methods=["GET"])(HealthController.get_acknowledged_errors)
health_bp.route("/<site_name>/health/errors/acknowledge", methods=["POST"])(HealthController.acknowledge_error)
health_bp.route("/<site_name>/health/errors/acknowledge/<fingerprint>", methods=["DELETE"])(HealthController.unacknowledge_error)
health_bp.route("/<site_name>/health/diffs/accepted", methods=["GET"])(HealthController.get_accepted_visual_diffs)
health_bp.route("/<site_name>/health/diffs/accept", methods=["POST"])(HealthController.accept_visual_diff)
health_bp.route("/<site_name>/health/diffs/accept/<check_id>", methods=["DELETE"])(HealthController.unaccept_visual_diff)


