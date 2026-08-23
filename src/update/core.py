import time
import uuid
from typing import Dict, Any, Optional
from src.api.tasks import set_task_progress
from src.wp.cache import CacheManager

class CoreUpdater:
    """
    Handles WordPress core updates with health checks, backups, and automatic rollback.
    """

    def __init__(
        self,
        wp_cli: Any,
        backup_manager: Any,
        health_manager: Any,
        site_config: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
        executor: Any = None,
        cache_manager: Optional[CacheManager] = None
    ):
        self.wp_cli = wp_cli
        self.backup_manager = backup_manager
        self.health_manager = health_manager
        self.site_config = site_config or {}
        self.credentials = credentials or {}
        self.executor = executor
        self.cache_manager = cache_manager or CacheManager(self.site_config, wp_cli)

    def check_updates(self) -> Dict[str, Any]:
        """Alias for check_update to standardize interface across updaters."""
        return self.check_update()

    def check_update(self) -> Dict[str, Any]:
        """
        Check if a WordPress core update is available.

        Returns:
            Dict[str, Any]: Dictionary containing update availability and version details.
        """
        try:
            res = self.wp_cli.run_command(["core", "check-update"], parse_json=True)
            if res.success and res.data:
                updates = res.data if isinstance(res.data, list) else []
                if updates:
                    return {"update_available": True, "details": updates[0]}
            return {"update_available": False, "details": None}
        except Exception as e:
            return {"update_available": False, "error": str(e)}

    def update(
        self,
        major: bool = False,
        timestamp: Optional[str] = None,
        create_backup: bool = True,
        quality_checks: bool = True,
        bypass_checks: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Update WordPress core. Runs health checks and auto-rolls back if check fails.

        Parameters:
            major (bool): Whether to perform a major update.
            timestamp (Optional[str]): Shared timestamp for logging.
            create_backup (bool): Whether to create a pre-update backup snapshot.
            quality_checks (bool): Whether to run pre/post update health checks.
            bypass_checks (Optional[bool]): Legacy flag to skip both backup and health checks.

        Returns:
            Dict[str, Any]: Dictionary containing status and details of the update.
        """
        if bypass_checks is True:
            create_backup = False
            quality_checks = False

        site_name = self.backup_manager.site_name
        update_id = f"core_update_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
        timestamp_val = timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        pre_report = None
        pre_status = "bypassed"
        pre_http = {}

        # 1. Pre-update quality check (if enabled)
        if quality_checks:
            set_task_progress("Capturing baseline site health snapshot before core update...")
            try:
                pre_report = self.health_manager.run_all_checks()
                pre_status = pre_report.get("overall_status", "unknown")
                pre_http = pre_report.get("checks", {}).get("http", {})
                if pre_http.get("status_code", 0) == 0:
                    return {
                        "update_id": update_id,
                        "site_name": site_name,
                        "timestamp": timestamp_val,
                        "type": "core",
                        "target": "core",
                        "backup_id": None,
                        "pre_update_health": pre_status,
                        "post_update_health": pre_status,
                        "status": "failed",
                        "rollback_triggered": False,
                        "error": "Abort: WordPress site is completely offline or unreachable before starting update (status code 0)."
                    }
            except Exception as e:
                set_task_progress(f"Warning: Pre-update quality check failed: {e}")

        # 2. Pre-update backup (if enabled)
        backup_id = None
        if create_backup:
            set_task_progress("Creating pre-update backup snapshot...")
            try:
                backup_manifest = self.backup_manager.create_backup(
                    description=f"Pre-core-update backup ({update_id})",
                    suffix="core"
                )
                backup_id = backup_manifest["backup_id"]
            except Exception as e:
                return {
                    "update_id": update_id,
                    "site_name": site_name,
                    "timestamp": timestamp_val,
                    "type": "core",
                    "target": "core",
                    "backup_id": None,
                    "pre_update_health": pre_status,
                    "post_update_health": pre_status,
                    "status": "failed",
                    "rollback_triggered": False,
                    "error": f"Abort: Failed to create pre-update backup: {e}"
                }

        # 3. Perform update
        set_task_progress("Updating WordPress core via WP-CLI...")
        args = ["core", "update"]
        if not major:
            args.append("--minor")

        update_res = self.wp_cli.run_command(args)

        if not update_res.success:
            set_task_progress("Core update command failed!")
            rollback_ok = False
            rollback_err = None
            if backup_id:
                set_task_progress("Initiating automatic rollback to pre-update backup...")
                try:
                    rollback_ok = self.backup_manager.restore_backup(backup_id)
                except Exception as re:
                    rollback_err = str(re)

            return {
                "update_id": update_id,
                "site_name": site_name,
                "timestamp": timestamp_val,
                "type": "core",
                "target": "core",
                "backup_id": backup_id,
                "pre_update_health": pre_status,
                "post_update_health": "critical",
                "status": "rolled_back" if rollback_ok else "failed",
                "rollback_triggered": bool(backup_id),
                "error": f"WordPress core update command failed: {update_res.stderr}."
            }

        # 4. Clear Elementor, caching plugin, and object caches before post-update snapshot comparison
        set_task_progress("Clearing site caches and refreshing assets...")
        cache_flush_res = self.cache_manager.clear_all_caches()

        # 5. Post-update quality checks or mandatory screenshot refresh
        post_status = "completed"
        if quality_checks and pre_report:
            set_task_progress("Verifying site health after update...")
            post_report = self.health_manager.run_all_checks(baseline_check_id=pre_report["id"])
            post_status = post_report.get("overall_status", "unknown")
            post_http = post_report.get("checks", {}).get("http", {})

            db_failed = (
                post_report.get("checks", {}).get("database", {}).get("connection") == "failed" and
                pre_report.get("checks", {}).get("database", {}).get("connection") != "failed"
            )
            status_code_failed = (
                post_http.get("status_code", 0) > 302 and
                post_http.get("status_code", 0) != pre_http.get("status_code", 0)
            )
            console_errors_failed = not post_http.get("console_errors_matched", True)
            screenshots_failed = not post_http.get("screenshot_diffs", {}).get("matched", True)
            asset_issues_failed = not post_http.get("asset_issues_matched", True)

            post_healthy = not (db_failed or status_code_failed or console_errors_failed or screenshots_failed or asset_issues_failed)

            if not post_healthy:
                set_task_progress("Post-update health check degraded! Initiating rollback...")
                rollback_ok = False
                rollback_err = None
                if backup_id:
                    try:
                        rollback_ok = self.backup_manager.restore_backup(backup_id)
                    except Exception as re:
                        rollback_err = str(re)

                return {
                    "update_id": update_id,
                    "site_name": site_name,
                    "timestamp": timestamp_val,
                    "type": "core",
                    "target": "core",
                    "backup_id": backup_id,
                    "pre_update_health": pre_status,
                    "post_update_health": post_status,
                    "status": "rolled_back" if rollback_ok else "failed",
                    "rollback_triggered": bool(backup_id),
                    "cache_flush": cache_flush_res,
                    "error": f"Post-update health check degraded. Rollback status: {'Success' if rollback_ok else f'Failed: {rollback_err}'}"
                }
        elif quality_checks:
            # Always re-capture post-update Playwright screenshots & refresh JSON
            set_task_progress("Re-capturing live site screenshots post-update...")
            try:
                self.health_manager.run_all_checks()
            except Exception as e:
                console_debug = f"Post-update screenshot refresh failed: {e}"

        set_task_progress("WordPress core updated successfully!")
        return {
            "update_id": update_id,
            "site_name": site_name,
            "timestamp": timestamp_val,
            "type": "core",
            "target": "core",
            "backup_id": backup_id,
            "pre_update_health": pre_status,
            "post_update_health": post_status if quality_checks else "bypassed",
            "status": "completed",
            "rollback_triggered": False,
            "cache_flush": cache_flush_res,
            "error": None
        }

    def rollback(self, backup_id: str) -> bool:
        """Restore site from a given backup ID."""
        return self.backup_manager.restore_backup(backup_id)


