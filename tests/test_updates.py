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

    def _get_health_report(self, overall_status="healthy", status_code=200, db_connection="success", console_errors_matched=True, screenshot_diffs_matched=True):
        return {
            "id": "test_report_id",
            "overall_status": overall_status,
            "checks": {
                "http": {
                    "status_code": status_code,
                    "console_errors_matched": console_errors_matched,
                    "screenshot_diffs": {
                        "matched": screenshot_diffs_matched
                    }
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

    def test_update_all_stops_on_failure(self):
        # Setup pre-update check and backup
        self.mock_health_mgr.run_all_checks.return_value = self._get_health_report(overall_status="healthy")
        self.mock_backup_mgr.create_backup.return_value = {"backup_id": "test_backup_123"}
        
        # Mock core update command to fail
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=1, stdout="", stderr="Connection failed.", success=False
        )
        self.mock_backup_mgr.restore_backup.return_value = True
        
        # Run update_all
        res = self.manager.update_all()
        
        self.assertEqual(res["status"], "rolled_back")
        # Ensure only 1 step was recorded (plugin), themes/core not executed
        self.assertEqual(len(res["steps"]), 1)
        self.assertEqual(res["steps"][0]["type"], "plugin")

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
        self.mock_wp_cli.run_command.assert_called_once_with(["plugin", "update", "--all"])

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
        self.mock_wp_cli.run_command.assert_called_once_with(["theme", "update", "--all"])

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

if __name__ == "__main__":
    unittest.main()
