import unittest
from unittest.mock import MagicMock, patch
import os
import json
import tempfile
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.base import CommandResult
from src.update.core import CoreUpdater
from src.update.plugins import PluginUpdater
from src.update.themes import ThemeUpdater
from src.update.manager import UpdateManager

class TestUpdates(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.site_config = {
            "site_name": "test-site",
            "db_host": "localhost",
            "db_name": "db",
            "db_user": "user",
            "wp_path": "/var/www/html",
            "health_check_url": "http://example.com"
        }
        self.credentials = {"db_password": "pwd"}
        
        self.mock_executor = MagicMock()
        self.mock_wp_cli = MagicMock()
        
        # We will mock the BackupManager and HealthCheckManager instances
        self.mock_backup_mgr = MagicMock()
        self.mock_health_mgr = MagicMock()
        
        # Patch BackupManager and HealthCheckManager instantiation in UpdateManager
        self.backup_mgr_patcher = patch("src.update.manager.BackupManager", return_value=self.mock_backup_mgr)
        self.health_mgr_patcher = patch("src.update.manager.HealthCheckManager", return_value=self.mock_health_mgr)
        
        self.mock_backup_class = self.backup_mgr_patcher.start()
        self.mock_health_class = self.health_mgr_patcher.start()
        
        # Create UpdateManager instance
        self.manager = UpdateManager(self.site_config, self.credentials, self.mock_executor, self.mock_wp_cli)
        
        # Override directories to temp directory
        self.manager.updates_log_dir = self.temp_dir
        self.manager.log_file = os.path.join(self.temp_dir, "test-site.jsonl")
        
        # Configure site name on mock backup manager (as Core/Plugin updaters use it)
        self.mock_backup_mgr.site_name = "test-site"

    def tearDown(self):
        self.backup_mgr_patcher.stop()
        self.health_mgr_patcher.stop()
        shutil.rmtree(self.temp_dir)

    def _get_health_report(self, overall_status="healthy", status_code=200, db_connection="success", console_errors_matched=True, screenshot_diffs_matched=True, asset_issues_matched=True):
        return {
            "id": "test_report_id",
            "overall_status": overall_status,
            "checks": {
                "http": {
                    "status_code": status_code,
                    "console_errors_matched": console_errors_matched,
                    "screenshot_diffs": {
                        "matched": screenshot_diffs_matched
                    },
                    "asset_issues_matched": asset_issues_matched
                },
                "database": {
                    "connection": db_connection
                }
            }
        }

    def test_core_update_successful(self):
        # 1. Setup health checks to return healthy snapshots
        self.mock_health_mgr.run_all_checks.side_effect = [
            self._get_health_report(overall_status="healthy"),
            self._get_health_report(overall_status="healthy")
        ]
        
        # 2. Setup backup manager to return manifest
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "test_backup_123"}
        
        # 3. Setup WP-CLI update command to return success
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=0, stdout="WordPress updated successfully.", stderr="", success=True
        )
        
        # Run update
        result = self.manager.update_core(major=False)
        
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["backup_id"], "test_backup_123")
        self.assertFalse(result["rollback_triggered"])
        
        # Verify call order
        self.assertEqual(self.mock_health_mgr.run_all_checks.call_count, 2)
        self.mock_backup_mgr.create_backup.assert_called_once()
        self.mock_wp_cli.run_command.assert_any_call(["core", "update", "--minor"])

    def test_core_update_failed_and_rolled_back(self):
        # 1. Pre-update check passes, post-update fails (screenshot mismatch)
        self.mock_health_mgr.run_all_checks.side_effect = [
            self._get_health_report(overall_status="healthy"),
            self._get_health_report(overall_status="degraded", screenshot_diffs_matched=False)
        ]
        
        # 2. Backup succeeds
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "test_backup_123"}
        
        # 3. WP-CLI update succeeds
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=0, stdout="WordPress updated successfully.", stderr="", success=True
        )
        
        # 5. Backup restore succeeds
        self.mock_backup_mgr.restore_backup.return_value = True
        
        # Run update
        result = self.manager.update_core(major=False)
        
        self.assertEqual(result["status"], "rolled_back")
        self.assertTrue(result["rollback_triggered"])
        self.mock_backup_mgr.restore_backup.assert_called_once_with("test_backup_123")

    def test_core_update_rolled_back_on_new_broken_image(self):
        # Pre-update check passes; post-update finds a broken image that wasn't there before
        self.mock_health_mgr.run_all_checks.side_effect = [
            self._get_health_report(overall_status="healthy"),
            self._get_health_report(overall_status="degraded", asset_issues_matched=False)
        ]

        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "test_backup_123"}
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=0, stdout="WordPress updated successfully.", stderr="", success=True
        )
        self.mock_backup_mgr.restore_backup.return_value = True

        result = self.manager.update_core(major=False)

        self.assertEqual(result["status"], "rolled_back")
        self.assertTrue(result["rollback_triggered"])
        self.mock_backup_mgr.restore_backup.assert_called_once_with("test_backup_123")

    def test_update_all_continues_after_failure(self):
        # Setup pre-update check and backup
        self.mock_health_mgr.run_all_checks.return_value = self._get_health_report(overall_status="healthy")
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "test_backup_123"}
        
        # Mock plugin WP-CLI update command to fail on plugins, but allow subsequent commands to succeed or fail
        def mock_run_command(cmd, **kwargs):
            if cmd and cmd[0] == "plugin":
                return CommandResult(exit_code=1, stdout="", stderr="Connection failed.", success=False)
            return CommandResult(exit_code=0, stdout="Success.", stderr="", success=True)
            
        self.mock_wp_cli.run_command.side_effect = mock_run_command
        self.mock_backup_mgr.restore_backup.return_value = True
        
        # Run update_all
        res = self.manager.update_all()
        
        self.assertEqual(res["status"], "rolled_back")
        # Ensure all 3 steps were recorded (plugin, theme, core) even after plugin failure
        self.assertEqual(len(res["steps"]), 3)
        self.assertEqual(res["steps"][0]["type"], "plugin")
        self.assertEqual(res["steps"][1]["type"], "theme")
        self.assertEqual(res["steps"][2]["type"], "core")

    def test_update_core_reraises_original_error_even_if_history_write_fails(self):
        """
        _write_history_best_effort must swallow a failure in the history write
        itself so it doesn't mask the update failure that's being reported.
        """
        self.manager.core_updater.update = MagicMock(side_effect=RuntimeError("core update boom"))
        with patch.object(self.manager, "_write_history", side_effect=OSError("disk full")):
            with self.assertRaises(RuntimeError) as ctx:
                self.manager.update_core(major=False)
        self.assertEqual(str(ctx.exception), "core update boom")

    def test_update_core_writes_failure_history_record(self):
        self.manager.core_updater.update = MagicMock(side_effect=RuntimeError("core update boom"))
        with self.assertRaises(RuntimeError):
            self.manager.update_core(major=False)

        with open(self.manager.log_file, "r", encoding="utf-8") as f:
            record = json.loads(f.readline())
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["type"], "core")
        self.assertIn("core update boom", record["error"])

    def test_plugin_check_updates(self):
        self.mock_wp_cli.check_plugin_updates.return_value = [{"name": "akismet", "version": "5.0", "update_version": "5.1"}]
        res = self.manager.plugin_updater.check_updates()
        self.assertTrue(res["updates_available"])
        self.assertEqual(len(res["plugins"]), 1)
        self.mock_wp_cli.check_plugin_updates.assert_called_once()

    def test_plugin_update_successful(self):
        self.mock_health_mgr.run_all_checks.side_effect = [
            self._get_health_report(overall_status="healthy"),
            self._get_health_report(overall_status="healthy")
        ]
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "plugin_backup_123"}
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=0, stdout="Plugin updated successfully.", stderr="", success=True
        )
        
        result = self.manager.update_plugins(plugin="akismet")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["backup_id"], "plugin_backup_123")
        self.assertFalse(result["rollback_triggered"])
        self.mock_wp_cli.run_command.assert_any_call(["plugin", "update", "akismet"])

    def test_plugin_update_failed_and_rolled_back(self):
        self.mock_health_mgr.run_all_checks.side_effect = [
            self._get_health_report(overall_status="healthy"),
            self._get_health_report(overall_status="degraded", screenshot_diffs_matched=False)
        ]
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "plugin_backup_123"}
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=0, stdout="Plugin updated successfully.", stderr="", success=True
        )
        self.mock_backup_mgr.restore_backup.return_value = True
        
        result = self.manager.update_plugins(plugin=None)
        self.assertEqual(result["status"], "rolled_back")
        self.assertTrue(result["rollback_triggered"])
        self.mock_backup_mgr.restore_backup.assert_called_once_with("plugin_backup_123")
        self.mock_wp_cli.run_command.assert_any_call(["plugin", "update", "--all"])

    def test_theme_check_updates(self):
        self.mock_wp_cli.check_theme_updates.return_value = [{"name": "twentytwenty", "version": "2.0", "update_version": "2.1"}]
        res = self.manager.theme_updater.check_updates()
        self.assertTrue(res["updates_available"])
        self.assertEqual(len(res["themes"]), 1)
        self.mock_wp_cli.check_theme_updates.assert_called_once()

    def test_theme_update_successful(self):
        self.mock_health_mgr.run_all_checks.side_effect = [
            self._get_health_report(overall_status="healthy"),
            self._get_health_report(overall_status="healthy")
        ]
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "theme_backup_123"}
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=0, stdout="Theme updated successfully.", stderr="", success=True
        )
        
        result = self.manager.update_themes(theme="twentytwenty")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["backup_id"], "theme_backup_123")
        self.assertFalse(result["rollback_triggered"])
        self.mock_wp_cli.run_command.assert_any_call(["theme", "update", "twentytwenty"])

    def test_theme_update_failed_and_rolled_back(self):
        self.mock_health_mgr.run_all_checks.side_effect = [
            self._get_health_report(overall_status="healthy"),
            self._get_health_report(overall_status="degraded", screenshot_diffs_matched=False)
        ]
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "theme_backup_123"}
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=0, stdout="Theme updated successfully.", stderr="", success=True
        )
        self.mock_backup_mgr.restore_backup.return_value = True
        
        result = self.manager.update_themes(theme=None)
        self.assertEqual(result["status"], "rolled_back")
        self.assertTrue(result["rollback_triggered"])
        self.mock_backup_mgr.restore_backup.assert_called_once_with("theme_backup_123")
        self.mock_wp_cli.run_command.assert_any_call(["theme", "update", "--all"])

    def test_updater_rollback_methods(self):
        self.mock_backup_mgr.restore_backup.return_value = True
        
        res1 = self.manager.core_updater.rollback("backup_1")
        self.assertTrue(res1)
        self.mock_backup_mgr.restore_backup.assert_any_call("backup_1")
        
        res2 = self.manager.plugin_updater.rollback("backup_2")
        self.assertTrue(res2)
        self.mock_backup_mgr.restore_backup.assert_any_call("backup_2")
        
        res3 = self.manager.theme_updater.rollback("backup_3")
        self.assertTrue(res3)
        self.mock_backup_mgr.restore_backup.assert_any_call("backup_3")

    def test_core_update_bypass_checks(self):
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=0, stdout="WordPress updated successfully.", stderr="", success=True
        )
        result = self.manager.update_core(major=False, bypass_checks=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["pre_update_health"], "bypassed")
        self.assertEqual(result["post_update_health"], "bypassed")
        self.assertIsNone(result["backup_id"])
        self.mock_health_mgr.run_all_checks.assert_not_called()
        self.mock_backup_mgr.create_backup.assert_not_called()

    def test_update_caching(self):
        # Ensure cache path contains our site slug
        cache_path = self.manager.get_cached_updates_path()
        self.assertIn("last_check_test-site.json", cache_path)
        
        # Test saving and loading cache
        sample_data = {"site_name": "test-site", "core": {"update_available": True}}
        self.manager.save_cached_updates(sample_data)
        
        self.assertTrue(os.path.exists(cache_path))
        
        # Test clear cache
        self.manager.clear_cached_updates()
        self.assertFalse(os.path.exists(cache_path))

    def test_cache_manager_flushes_elementor_and_caching_plugins(self):
        from src.wp.cache import CacheManager
        
        cache_mgr = CacheManager(self.site_config, self.mock_wp_cli)
        self.mock_wp_cli.list_plugins.return_value = [
            {"name": "elementor", "status": "active"},
            {"name": "wp-rocket", "status": "active"},
            {"name": "akismet", "status": "inactive"}
        ]
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=0, stdout="Success.", stderr="", success=True
        )
        
        res = cache_mgr.clear_all_caches()
        self.assertTrue(res["success"])
        self.assertFalse(res["has_warnings"])
        self.assertIsNone(res["admin_url"])
        
        # Check that update-db, elementor flush-css, wp-rocket clean, and cache flush were invoked
        self.mock_wp_cli.run_command.assert_any_call(["core", "update-db"])
        self.mock_wp_cli.run_command.assert_any_call(["elementor", "flush-css"])
        self.mock_wp_cli.run_command.assert_any_call(["rocket", "clean", "--confirm"])
        self.mock_wp_cli.run_command.assert_any_call(["cache", "flush"])

    def test_cache_manager_triggers_admin_init_as_administrator(self):
        from src.wp.cache import CacheManager

        cache_mgr = CacheManager(self.site_config, self.mock_wp_cli)
        self.mock_wp_cli.list_plugins.return_value = []

        def mock_cmd(cmd, **kwargs):
            if cmd == ["user", "list", "--role=administrator", "--field=ID", "--number=1"]:
                return CommandResult(exit_code=0, stdout="7\n", stderr="", success=True)
            if cmd == ["eval", "wp_set_current_user(7); do_action('admin_init');"]:
                return CommandResult(exit_code=0, stdout="", stderr="", success=True)
            return CommandResult(exit_code=0, stdout="Success.", stderr="", success=True)

        self.mock_wp_cli.run_command.side_effect = mock_cmd
        res = cache_mgr.clear_all_caches()

        self.assertTrue(res["admin_init_migrations"]["success"])
        self.mock_wp_cli.run_command.assert_any_call(["user", "list", "--role=administrator", "--field=ID", "--number=1"])
        self.mock_wp_cli.run_command.assert_any_call(["eval", "wp_set_current_user(7); do_action('admin_init');"])

    def test_cache_manager_admin_init_failure_does_not_count_as_warning(self):
        from src.wp.cache import CacheManager

        cache_mgr = CacheManager(self.site_config, self.mock_wp_cli)
        self.mock_wp_cli.list_plugins.return_value = []

        def mock_cmd(cmd, **kwargs):
            if cmd == ["user", "list", "--role=administrator", "--field=ID", "--number=1"]:
                # No administrator found on this site
                return CommandResult(exit_code=0, stdout="", stderr="", success=True)
            return CommandResult(exit_code=0, stdout="Success.", stderr="", success=True)

        self.mock_wp_cli.run_command.side_effect = mock_cmd
        res = cache_mgr.clear_all_caches()

        # A missing admin_init trigger is expected/benign, not a cache-flush warning
        self.assertFalse(res["admin_init_migrations"]["success"])
        self.assertTrue(res["success"])
        self.assertFalse(res["has_warnings"])

    def test_cache_manager_warning_generates_admin_url(self):
        from src.wp.cache import CacheManager
        
        cache_mgr = CacheManager(self.site_config, self.mock_wp_cli)
        self.mock_wp_cli.list_plugins.return_value = [
            {"name": "elementor", "status": "active"}
        ]
        def mock_cmd(cmd, **kwargs):
            if cmd == ["elementor", "flush-css"]:
                return CommandResult(exit_code=1, stdout="", stderr="Error: elementor command not found", success=False)
            return CommandResult(exit_code=0, stdout="Success", stderr="", success=True)
            
        self.mock_wp_cli.run_command.side_effect = mock_cmd
        res = cache_mgr.clear_all_caches()
        
        self.assertFalse(res["success"])
        self.assertTrue(res["has_warnings"])
        self.assertEqual(len(res["warnings"]), 1)
        self.assertEqual(res["admin_url"], "http://example.com/wp-admin")

    def test_core_update_flushes_cache_before_health_check(self):
        call_order = []
        
        def mock_run_all_checks(**kwargs):
            call_order.append("health_check")
            return self._get_health_report(overall_status="healthy")
            
        def mock_run_command(cmd, **kwargs):
            if cmd == ["core", "update", "--minor"]:
                call_order.append("core_update")
            elif cmd == ["cache", "flush"]:
                call_order.append("cache_flush")
            return CommandResult(exit_code=0, stdout="Success.", stderr="", success=True)
            
        self.mock_health_mgr.run_all_checks.side_effect = mock_run_all_checks
        self.mock_wp_cli.run_command.side_effect = mock_run_command
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "test_backup"}
        
        res = self.manager.update_core(major=False)
        self.assertEqual(res["status"], "completed")
        self.assertIn("cache_flush", res)
        
        # Verify order: pre health_check -> core_update -> cache_flush -> post health_check
        self.assertEqual(call_order, ["health_check", "core_update", "cache_flush", "health_check"])

    def test_plugin_update_flushes_cache_before_health_check(self):
        call_order = []

        def mock_run_all_checks(**kwargs):
            call_order.append("health_check")
            return self._get_health_report(overall_status="healthy")

        def mock_run_command(cmd, **kwargs):
            if cmd == ["plugin", "update", "--all"]:
                call_order.append("plugin_update")
            elif cmd == ["cache", "flush"]:
                call_order.append("cache_flush")
            return CommandResult(exit_code=0, stdout="Success.", stderr="", success=True)

        self.mock_health_mgr.run_all_checks.side_effect = mock_run_all_checks
        self.mock_wp_cli.run_command.side_effect = mock_run_command
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "test_backup"}

        res = self.manager.update_plugins(plugin=None)
        self.assertEqual(res["status"], "completed")
        self.assertIn("cache_flush", res)

        # Verify order: pre health_check -> plugin_update -> cache_flush -> post health_check
        self.assertEqual(call_order, ["health_check", "plugin_update", "cache_flush", "health_check"])

    def test_theme_update_flushes_cache_before_health_check(self):
        call_order = []

        def mock_run_all_checks(**kwargs):
            call_order.append("health_check")
            return self._get_health_report(overall_status="healthy")

        def mock_run_command(cmd, **kwargs):
            if cmd == ["theme", "update", "--all"]:
                call_order.append("theme_update")
            elif cmd == ["cache", "flush"]:
                call_order.append("cache_flush")
            return CommandResult(exit_code=0, stdout="Success.", stderr="", success=True)

        self.mock_health_mgr.run_all_checks.side_effect = mock_run_all_checks
        self.mock_wp_cli.run_command.side_effect = mock_run_command
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "test_backup"}

        res = self.manager.update_themes(theme=None)
        self.assertEqual(res["status"], "completed")
        self.assertIn("cache_flush", res)

        # Verify order: pre health_check -> theme_update -> cache_flush -> post health_check
        self.assertEqual(call_order, ["health_check", "theme_update", "cache_flush", "health_check"])

    def test_is_stale_logic(self):
        import time
        from src.api.routes.updates import UpdatesController

        # Empty or None timestamp is stale
        self.assertTrue(UpdatesController._is_stale(None))
        self.assertTrue(UpdatesController._is_stale(""))

        # Fresh timestamp (current time) is not stale
        now_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.assertFalse(UpdatesController._is_stale(now_ts))

        # Stale timestamp (2 days ago) is stale
        old_time = time.gmtime(time.time() - (2 * 24 * 3600))
        old_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", old_time)
        self.assertTrue(UpdatesController._is_stale(old_ts))

if __name__ == "__main__":
    unittest.main()
