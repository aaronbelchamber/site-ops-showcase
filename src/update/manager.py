import os
import json
import time
import uuid
from typing import Dict, Any, List, Optional
from src.wp.cli import WPCLI
from src.backup.manager import BackupManager
from src.health.manager import HealthCheckManager
from src.execution.base import BaseExecutor
from src.wp.cache import CacheManager
from src.update.core import CoreUpdater
from src.update.plugins import PluginUpdater
from src.update.themes import ThemeUpdater
from src.git.manager import GitManager
from src.logging.logger import logger

class UpdateManager:
    def __init__(self, site_config: Dict[str, Any], credentials: Dict[str, Any], executor: BaseExecutor, wp_cli: WPCLI):
        self.site_config = site_config
        self.credentials = credentials
        self.executor = executor
        self.wp_cli = wp_cli
        self.site_name = site_config["site_name"]
        
        # Initialize dependencies
        self.backup_manager = BackupManager(site_config, credentials, executor)
        self.health_manager = HealthCheckManager(site_config, executor, wp_cli)
        self.cache_manager = CacheManager(site_config, wp_cli)
        self.git_manager = GitManager(site_config, executor)
        
        # Initialize updater components
        self.core_updater = CoreUpdater(wp_cli, self.backup_manager, self.health_manager, site_config=site_config, credentials=credentials, executor=executor, cache_manager=self.cache_manager)
        self.plugin_updater = PluginUpdater(wp_cli, self.backup_manager, self.health_manager, site_config=site_config, credentials=credentials, executor=executor, cache_manager=self.cache_manager)
        self.theme_updater = ThemeUpdater(wp_cli, self.backup_manager, self.health_manager, site_config=site_config, credentials=credentials, executor=executor, cache_manager=self.cache_manager)
        
        # Log directory
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(src_dir)
        self.updates_log_dir = os.path.join(project_root, "logs", "updates")
        self.log_file = os.path.join(self.updates_log_dir, f"{self.site_name}.jsonl")

    def capture_versions(self) -> Dict[str, Any]:
        """Capture currently installed core, plugin, and theme versions."""
        versions = {
            "core_version": None,
            "plugins": {},
            "themes": {}
        }
        try:
            core_res = self.wp_cli.run_command(["core", "version"])
            if core_res.success and core_res.stdout:
                versions["core_version"] = core_res.stdout.strip()
        except Exception as e:
            logger.warning(f"Could not capture core version for '{self.site_name}': {e}. "
                            f"Before/after version diff for this update will be missing core.")

        try:
            plugins_res = self.wp_cli.run_command(["plugin", "list", "--fields=name,version"], parse_json=True)
            if plugins_res.success and isinstance(plugins_res.data, list):
                for p in plugins_res.data:
                    if isinstance(p, dict) and "name" in p and "version" in p:
                        versions["plugins"][p["name"]] = p["version"]
        except Exception as e:
            logger.warning(f"Could not capture plugin versions for '{self.site_name}': {e}. "
                            f"Before/after version diff for this update will be missing plugins.")

        try:
            themes_res = self.wp_cli.run_command(["theme", "list", "--fields=name,version"], parse_json=True)
            if themes_res.success and isinstance(themes_res.data, list):
                for t in themes_res.data:
                    if isinstance(t, dict) and "name" in t and "version" in t:
                        versions["themes"][t["name"]] = t["version"]
        except Exception as e:
            logger.warning(f"Could not capture theme versions for '{self.site_name}': {e}. "
                            f"Before/after version diff for this update will be missing themes.")

        return versions

    def _handle_git_integration(
        self,
        update_res: Dict[str, Any],
        versions_before: Optional[Dict[str, Any]] = None,
        versions_after: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Handle Git commit and push if git is enabled and initialized."""
        if not self.site_config.get("git_enabled", True):
            return None
        if not self.site_config.get("git_auto_commit", True):
            return None
        if update_res.get("status") != "completed":
            return None

        try:
            if not self.git_manager.is_initialized():
                return None

            commit_info = self.git_manager.create_update_commit(
                update_res,
                versions_before=versions_before,
                versions_after=versions_after
            )
            git_data = {
                "commit": commit_info.get("commit"),
                "commit_message": commit_info.get("message"),
                "commit_success": commit_info.get("success", False)
            }

            if self.site_config.get("git_auto_push", True) and commit_info.get("success"):
                push_info = self.git_manager.push_to_github()
                git_data["push_success"] = push_info.get("success", False)
                if not push_info.get("success"):
                    git_data["push_error"] = push_info.get("error")

            return git_data
        except Exception as e:
            return {"commit_success": False, "error": str(e)}

    def _write_history(self, record: Dict[str, Any]) -> None:
        """Append an update record to the site's update history JSONL file."""
        os.makedirs(self.updates_log_dir, exist_ok=True)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _write_history_best_effort(self, record: Dict[str, Any], original_error: Exception) -> None:
        """
        Write a failure record to update history without letting a history-write
        failure mask the original update failure that's about to be re-raised.
        """
        try:
            self._write_history(record)
        except Exception as history_err:
            logger.error(f"Could not write failure record to update history for '{self.site_name}': "
                          f"{history_err}. The underlying update failure was: {original_error}")

    def get_cached_updates_path(self) -> str:
        """Get the path to the cached updates JSON file."""
        return os.path.join(self.updates_log_dir, f"last_check_{self.site_name}.json")

    def save_cached_updates(self, updates_data: Dict[str, Any]) -> None:
        """Save updates check result to cache file."""
        os.makedirs(self.updates_log_dir, exist_ok=True)
        path = self.get_cached_updates_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(updates_data, f, indent=2)

    def clear_cached_updates(self) -> None:
        """Remove the cached updates file."""
        path = self.get_cached_updates_path()
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                # File already deleted or unreadable; best-effort cleanup. Next cache write will replace it.
                pass

    def update_cache_after_success(self, update_type: str) -> None:
        """Update cached updates file to mark the updated component as clean."""
        path = self.get_cached_updates_path()
        cached_data = {
            "site_name": self.site_name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "core": {"update_available": False, "details": None},
            "plugins": {"updates_available": False, "plugins": []},
            "themes": {"updates_available": False, "themes": []}
        }
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cached_data["core"] = data.get("core", cached_data["core"])
                    cached_data["plugins"] = data.get("plugins", cached_data["plugins"])
                    cached_data["themes"] = data.get("themes", cached_data["themes"])
            except Exception:
                # Cache file corrupted or unreadable; best-effort read. Rebuild with defaults and mark current component as clean.
                pass
                
        if update_type == "core":
            cached_data["core"] = {"update_available": False, "details": None}
        elif update_type == "plugin":
            cached_data["plugins"] = {"updates_available": False, "plugins": []}
        elif update_type == "theme":
            cached_data["themes"] = {"updates_available": False, "themes": []}
        elif update_type == "all":
            cached_data["core"] = {"update_available": False, "details": None}
            cached_data["plugins"] = {"updates_available": False, "plugins": []}
            cached_data["themes"] = {"updates_available": False, "themes": []}
            
        self.save_cached_updates(cached_data)

    def check_all_updates(self) -> Dict[str, Any]:
        """Check all available updates for core, plugins, and themes."""
        core_info = self.core_updater.check_updates()
        plugin_info = self.plugin_updater.check_updates()
        theme_info = self.theme_updater.check_updates()
        
        return {
            "site_name": self.site_name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "core": core_info,
            "plugins": plugin_info,
            "themes": theme_info
        }

    def _post_update_tasks(self) -> None:
        """Automate post-update tasks (database updates and cache flushing)."""
        time.sleep(1.0)
        try:
            self.cache_manager.clear_all_caches()
        except Exception as e:
            logger.warning(f"Could not clear caches for '{self.site_name}' after update: {e}. "
                            f"Stale cached content may still be served.")

    def update_core(self, major: bool = False, timestamp: Optional[str] = None, create_backup: bool = True, quality_checks: bool = True, bypass_checks: Optional[bool] = None) -> Dict[str, Any]:
        """Perform core update and record history."""
        versions_before = self.capture_versions()
        try:
            res = self.core_updater.update(major, timestamp=timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
            if res.get("status") == "completed":
                self.update_cache_after_success("core")
                versions_after = self.capture_versions()
                res["versions"] = {"before": versions_before, "after": versions_after}
                git_info = self._handle_git_integration(res, versions_before, versions_after)
                if git_info:
                    res["git"] = git_info
            self._write_history(res)
            return res
        except Exception as e:
            fallback_res = {
                "update_id": f"core_update_fail_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}",
                "site_name": self.site_name,
                "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "type": "core",
                "target": "core",
                "backup_id": None,
                "pre_update_health": "unknown",
                "post_update_health": "unknown",
                "status": "failed",
                "rollback_triggered": False,
                "error": str(e)
            }
            self._write_history_best_effort(fallback_res, e)
            raise e

    def update_plugins(self, plugin: Optional[str] = None, timestamp: Optional[str] = None, create_backup: bool = True, quality_checks: bool = True, bypass_checks: Optional[bool] = None) -> Dict[str, Any]:
        """Perform plugins update and record history."""
        versions_before = self.capture_versions()
        try:
            res = self.plugin_updater.update(plugin, timestamp=timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
            if res.get("status") == "completed":
                self.update_cache_after_success("plugin")
                versions_after = self.capture_versions()
                res["versions"] = {"before": versions_before, "after": versions_after}
                git_info = self._handle_git_integration(res, versions_before, versions_after)
                if git_info:
                    res["git"] = git_info
            self._write_history(res)
            return res
        except Exception as e:
            fallback_res = {
                "update_id": f"plugin_update_fail_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}",
                "site_name": self.site_name,
                "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "type": "plugin",
                "target": plugin or "all-plugins",
                "backup_id": None,
                "pre_update_health": "unknown",
                "post_update_health": "unknown",
                "status": "failed",
                "rollback_triggered": False,
                "error": str(e)
            }
            self._write_history_best_effort(fallback_res, e)
            raise e

    def update_themes(self, theme: Optional[str] = None, timestamp: Optional[str] = None, create_backup: bool = True, quality_checks: bool = True, bypass_checks: Optional[bool] = None) -> Dict[str, Any]:
        """Perform themes update and record history."""
        versions_before = self.capture_versions()
        try:
            res = self.theme_updater.update(theme, timestamp=timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
            if res.get("status") == "completed":
                self.update_cache_after_success("theme")
                versions_after = self.capture_versions()
                res["versions"] = {"before": versions_before, "after": versions_after}
                git_info = self._handle_git_integration(res, versions_before, versions_after)
                if git_info:
                    res["git"] = git_info
            self._write_history(res)
            return res
        except Exception as e:
            fallback_res = {
                "update_id": f"theme_update_fail_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}",
                "site_name": self.site_name,
                "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "type": "theme",
                "target": theme or "all-themes",
                "backup_id": None,
                "pre_update_health": "unknown",
                "post_update_health": "unknown",
                "status": "failed",
                "rollback_triggered": False,
                "error": str(e)
            }
            self._write_history_best_effort(fallback_res, e)
            raise e

    def update_all(self, create_backup: bool = True, quality_checks: bool = True, bypass_checks: Optional[bool] = None) -> Dict[str, Any]:
        """
        Sequentially perform core, plugin, and theme updates.
        Updates plugins, themes, and WordPress core unconditionally so that
        a failure in earlier steps does not skip remaining updates.
        Overall status reflects the worst status across all steps.
        """
        results = []
        shared_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        versions_before = self.capture_versions()
        
        try:
            # 1. Update Plugins
            plugin_res = self.update_plugins(plugin=None, timestamp=shared_timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
            results.append(plugin_res)
                
            # 2. Update Themes
            theme_res = self.update_themes(theme=None, timestamp=shared_timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
            results.append(theme_res)
                    
            # 3. Update Core
            core_res = self.update_core(major=False, timestamp=shared_timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
            results.append(core_res)
                    
            # Determine overall status: failed > rolled_back > completed
            statuses = [r.get("status") for r in results]
            if "failed" in statuses:
                overall_status = "failed"
            elif "rolled_back" in statuses:
                overall_status = "rolled_back"
            else:
                overall_status = "completed"

            versions_after = self.capture_versions()
            res = {
                "update_id": f"all_update_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}",
                "site_name": self.site_name,
                "timestamp": shared_timestamp,
                "type": "all",
                "target": "all",
                "backup_id": None,
                "pre_update_health": results[0].get("pre_update_health") if results else "healthy",
                "post_update_health": results[-1].get("post_update_health") if results else "healthy",
                "status": overall_status,
                "rollback_triggered": any(r.get("rollback_triggered", False) for r in results),
                "error": next((r.get("error") for r in results if r.get("error")), None),
                "steps": results,
                "versions": {"before": versions_before, "after": versions_after}
            }

            if overall_status == "completed":
                git_info = self._handle_git_integration(res, versions_before, versions_after)
                if git_info:
                    res["git"] = git_info

            self._write_history(res)
            return res
        except Exception as e:
            res = {
                "update_id": f"all_update_fail_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}",
                "site_name": self.site_name,
                "timestamp": shared_timestamp,
                "type": "all",
                "target": "all",
                "backup_id": None,
                "pre_update_health": "unknown",
                "post_update_health": "unknown",
                "status": "failed",
                "rollback_triggered": False,
                "error": str(e),
                "steps": results
            }
            self._write_history_best_effort(res, e)
            raise e

    def get_update_history(self, site_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get the site update execution history from the JSONL log file."""
        target_site = site_name or self.site_name
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(src_dir)
        log_file = os.path.join(project_root, "logs", "updates", f"{target_site}.jsonl")
        
        if not os.path.exists(log_file):
            return []
            
        history = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        history.append(json.loads(line))
                    except Exception as e:
                        logger.warning(f"Skipping corrupted update history line in '{log_file}': {e}")
                        
        # Sort descending by timestamp
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return history
