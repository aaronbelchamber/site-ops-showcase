import os
import json
import time
import uuid
from typing import Dict, Any, List, Optional
from src.wp.cli import WPCLI
from src.backup.manager import BackupManager
from src.health.manager import HealthCheckManager
from src.execution.base import BaseExecutor
from src.update.core import CoreUpdater
from src.update.plugins import PluginUpdater
from src.update.themes import ThemeUpdater

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
        
        # Initialize updater components
        self.core_updater = CoreUpdater(wp_cli, self.backup_manager, self.health_manager)
        self.plugin_updater = PluginUpdater(wp_cli, self.backup_manager, self.health_manager)
        self.theme_updater = ThemeUpdater(wp_cli, self.backup_manager, self.health_manager)
        
        # Log directory
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(src_dir)
        self.updates_log_dir = os.path.join(project_root, "logs", "updates")
        self.log_file = os.path.join(self.updates_log_dir, f"{self.site_name}.jsonl")

    def _write_history(self, record: Dict[str, Any]) -> None:
        """Append an update record to the site's update history JSONL file."""
        os.makedirs(self.updates_log_dir, exist_ok=True)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

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
            self.wp_cli.run_command(["core", "update-db"])
        except Exception:
            pass
        try:
            self.wp_cli.run_command(["cache", "flush"])
        except Exception:
            pass

    def update_core(self, major: bool = False, timestamp: Optional[str] = None, create_backup: bool = True, quality_checks: bool = True, bypass_checks: Optional[bool] = None) -> Dict[str, Any]:
        """Perform core update and record history."""
        try:
            res = self.core_updater.update(major, timestamp=timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
            self._write_history(res)
            if res.get("status") == "completed":
                self.update_cache_after_success("core")
                self._post_update_tasks()
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
            try:
                self._write_history(fallback_res)
            except Exception:
                pass
            raise e

    def update_plugins(self, plugin: Optional[str] = None, timestamp: Optional[str] = None, create_backup: bool = True, quality_checks: bool = True, bypass_checks: Optional[bool] = None) -> Dict[str, Any]:
        """Perform plugins update and record history."""
        try:
            res = self.plugin_updater.update(plugin, timestamp=timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
            self._write_history(res)
            if res.get("status") == "completed":
                self.update_cache_after_success("plugin")
                self._post_update_tasks()
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
            try:
                self._write_history(fallback_res)
            except Exception:
                pass
            raise e

    def update_themes(self, theme: Optional[str] = None, timestamp: Optional[str] = None, create_backup: bool = True, quality_checks: bool = True, bypass_checks: Optional[bool] = None) -> Dict[str, Any]:
        """Perform themes update and record history."""
        try:
            res = self.theme_updater.update(theme, timestamp=timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
            self._write_history(res)
            if res.get("status") == "completed":
                self.update_cache_after_success("theme")
                self._post_update_tasks()
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
            try:
                self._write_history(fallback_res)
            except Exception:
                pass
            raise e

    def update_all(self, create_backup: bool = True, quality_checks: bool = True, bypass_checks: Optional[bool] = None) -> Dict[str, Any]:
        """
        Sequentially perform core, plugin, and theme updates.
        Updates plugins and themes first, then WordPress core.
        Stops and rolls back immediately if any updates fail.
        """
        results = []
        overall_status = "completed"
        shared_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        try:
            # 1. Update Plugins
            plugin_res = self.update_plugins(plugin=None, timestamp=shared_timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
            results.append(plugin_res)
            if plugin_res["status"] in ["rolled_back", "failed"]:
                overall_status = plugin_res["status"]
                
            # 2. Update Themes if plugins succeeded
            if overall_status == "completed":
                theme_res = self.update_themes(theme=None, timestamp=shared_timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
                results.append(theme_res)
                if theme_res["status"] in ["rolled_back", "failed"]:
                    overall_status = theme_res["status"]
                    
            # 3. Update Core if plugins and themes succeeded
            if overall_status == "completed":
                core_res = self.update_core(major=False, timestamp=shared_timestamp, create_backup=create_backup, quality_checks=quality_checks, bypass_checks=bypass_checks)
                results.append(core_res)
                if core_res["status"] in ["rolled_back", "failed"]:
                    overall_status = core_res["status"]
                    
            # Cache clearing is automatically performed by sub-updaters called above
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
                "steps": results
            }
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
            try:
                self._write_history(res)
            except Exception:
                pass
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
                    except Exception:
                        pass
                        
        # Sort descending by timestamp
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return history
