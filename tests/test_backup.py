import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import json
import tempfile
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.base import CommandResult
from src.backup.database import DatabaseBackup
from src.backup.assets import AssetBackup
from src.backup.manager import BackupManager

class TestBackupComponents(unittest.TestCase):
    def setUp(self):
        self.mock_executor = MagicMock()
        self.temp_dir = tempfile.mkdtemp()
        self.db_config = {
            "host": "dbhost",
            "name": "dbname",
            "user": "dbuser",
            "password": "dbpass"
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_database_dump(self):
        db_backup = DatabaseBackup(self.mock_executor, self.db_config, self.temp_dir)
        
        # Mock execute_stream to simulate writing a file
        def fake_execute_stream(command, local_path):
            with open(local_path, "wb") as f:
                f.write(b"mocked_dump_data")
            return CommandResult(exit_code=0, stdout="", stderr="", success=True)
            
        self.mock_executor.execute_stream.side_effect = fake_execute_stream
        
        db_file = db_backup.dump()
        
        self.assertTrue(os.path.exists(db_file))
        self.assertTrue(db_file.endswith(".sql.gz"))
        self.assertEqual(os.path.dirname(db_file), self.temp_dir)
        
        # Check command
        args, kwargs = self.mock_executor.execute_stream.call_args
        cmd = args[0]
        self.assertIn("mysqldump", cmd)
        self.assertIn("MYSQL_PWD=dbpass", cmd)
        self.assertIn("-h dbhost", cmd)
        self.assertIn("dbname", cmd)

    def test_database_restore(self):
        db_backup = DatabaseBackup(self.mock_executor, self.db_config, self.temp_dir)
        
        # Create a dummy backup file
        dummy_file = os.path.join(self.temp_dir, "dummy.sql.gz")
        with open(dummy_file, "wb") as f:
            f.write(b"data")
            
        self.mock_executor.execute_stream_input.return_value = CommandResult(
            exit_code=0, stdout="", stderr="", success=True
        )
        
        restored = db_backup.restore(dummy_file)
        self.assertTrue(restored)
        
        # Check command
        args, kwargs = self.mock_executor.execute_stream_input.call_args
        cmd = args[0]
        self.assertIn("gunzip | MYSQL_PWD=dbpass mysql", cmd)
        self.assertEqual(args[1], dummy_file)

    def test_asset_archive_include_media(self):
        asset_backup = AssetBackup(self.mock_executor, "/var/www/html", self.temp_dir, include_media=True)
        
        def fake_execute_stream(command, local_path):
            with open(local_path, "wb") as f:
                f.write(b"mocked_tar_data")
            return CommandResult(exit_code=0, stdout="", stderr="", success=True)
            
        self.mock_executor.execute_stream.side_effect = fake_execute_stream
        
        tar_file = asset_backup.archive()
        
        self.assertTrue(os.path.exists(tar_file))
        self.assertTrue(tar_file.endswith(".tar.gz"))
        
        args, kwargs = self.mock_executor.execute_stream.call_args
        cmd = args[0]
        self.assertIn("tar -czf -", cmd)
        self.assertIn("wp-content/cache", cmd)
        self.assertNotIn("wp-content/uploads", cmd) # uploads NOT excluded

    def test_asset_archive_exclude_media(self):
        asset_backup = AssetBackup(self.mock_executor, "/var/www/html", self.temp_dir, include_media=False)
        
        def fake_execute_stream(command, local_path):
            with open(local_path, "wb") as f:
                f.write(b"mocked_tar_data")
            return CommandResult(exit_code=0, stdout="", stderr="", success=True)
            
        self.mock_executor.execute_stream.side_effect = fake_execute_stream
        
        tar_file = asset_backup.archive()
        
        args, kwargs = self.mock_executor.execute_stream.call_args
        cmd = args[0]
        self.assertIn("wp-content/uploads", cmd) # uploads excluded

    @patch("src.backup.assets.os.name", "nt")
    def test_asset_restore_win(self):
        from src.execution.local import LocalExecutor
        local_executor = LocalExecutor()
        local_executor.execute = MagicMock(return_value=CommandResult(
            exit_code=0, stdout="", stderr="", success=True
        ))
        
        asset_backup = AssetBackup(local_executor, "/var/www/html", self.temp_dir, include_media=True)
        
        dummy_backup = os.path.join(self.temp_dir, "backup.tar.gz")
        with open(dummy_backup, "wb") as f:
            f.write(b"data")
            
        restored = asset_backup.restore(dummy_backup, "/var/www/html")
        self.assertTrue(restored)
        
        args, kwargs = local_executor.execute.call_args
        cmd = args[0]
        self.assertIn("powershell -Command", cmd)
        self.assertIn("tar -xzf", cmd)

    def test_asset_restore_non_win(self):
        self.mock_executor.execute_stream_input.return_value = CommandResult(
            exit_code=0, stdout="", stderr="", success=True
        )
        
        asset_backup = AssetBackup(self.mock_executor, "/var/www/html", self.temp_dir, include_media=True)
        
        dummy_backup = os.path.join(self.temp_dir, "backup.tar.gz")
        with open(dummy_backup, "wb") as f:
            f.write(b"data")
            
        with patch("src.backup.assets.os.name", "posix"):
            restored = asset_backup.restore(dummy_backup, "/var/www/html")
            self.assertTrue(restored)
            
        args, kwargs = self.mock_executor.execute_stream_input.call_args
        cmd = args[0]
        self.assertIn("tar -xzf - -C", cmd)
        self.assertEqual(args[1], dummy_backup)

class TestBackupManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.site_config = {
            "site_name": "test-site-slug",
            "db_host": "localhost",
            "db_name": "wp_db",
            "db_user": "wp_user",
            "wp_path": "/var/www/wordpress",
            "include_media": True
        }
        self.credentials = {
            "db_password": "db_password_value"
        }
        self.mock_executor = MagicMock()
        
        # Override project root paths dynamically inside tests or let it use temp dir
        # In BackupManager, it calculates path relative to __file__.
        # We can patch os.path.join in BackupManager.__init__ or we can patch project_root.
        # Let's patch the manager's attributes directly after initialization
        self.manager = BackupManager(self.site_config, self.credentials, self.mock_executor)
        
        # Override manager dirs to point to temp dir
        self.manager.backups_base_dir = os.path.join(self.temp_dir, "backups", "test-site-slug")
        self.manager.db_dir = os.path.join(self.manager.backups_base_dir, "db")
        self.manager.assets_dir = os.path.join(self.manager.backups_base_dir, "assets")
        self.manager.manifests_dir = os.path.join(self.manager.backups_base_dir, "manifests")
        
        # Update components with modified directories
        self.manager.db_backup.local_backup_path = self.manager.db_dir
        self.manager.asset_backup.local_backup_path = self.manager.assets_dir

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("src.backup.database.DatabaseBackup.dump")
    @patch("src.backup.assets.AssetBackup.archive")
    def test_create_backup(self, mock_archive, mock_dump):
        # Setup mock file returns
        mock_db_file = os.path.join(self.manager.db_dir, "wp_db_123.sql.gz")
        mock_asset_file = os.path.join(self.manager.assets_dir, "wordpress_123.tar.gz")
        
        # Create dummy physical files so size checks succeed
        os.makedirs(self.manager.db_dir, exist_ok=True)
        os.makedirs(self.manager.assets_dir, exist_ok=True)
        with open(mock_db_file, "wb") as f: f.write(b"a" * 100)
        with open(mock_asset_file, "wb") as f: f.write(b"b" * 200)
        
        mock_dump.return_value = mock_db_file
        mock_archive.return_value = mock_asset_file
        
        manifest = self.manager.create_backup("Pre-upgrade")
        
        self.assertEqual(manifest["site_name"], "test-site-slug")
        self.assertEqual(manifest["description"], "Pre-upgrade")
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["size_bytes"], 300)
        self.assertEqual(manifest["include_media"], True)
        self.assertEqual(manifest["backup_type"], "Full")
        
        # Verify manifest file exists on disk
        manifest_file = os.path.join(self.manager.manifests_dir, f"{manifest['backup_id']}.json")
        self.assertTrue(os.path.exists(manifest_file))
        
        with open(manifest_file, "r") as f:
            loaded_manifest = json.load(f)
        self.assertEqual(loaded_manifest, manifest)

        # Test backup when no include_media override is specified: should fall back to site_config (True)
        config_default_manifest = self.manager.create_backup("Pre-upgrade-config-default")
        self.assertEqual(config_default_manifest["include_media"], True)
        self.assertEqual(config_default_manifest["backup_type"], "Full")

        # Test partial/exclude media backup
        partial_manifest = self.manager.create_backup("Pre-upgrade-partial", include_media=False)
        self.assertEqual(partial_manifest["include_media"], False)
        self.assertEqual(partial_manifest["backup_type"], "Partial")

        # Test default when include_media is not specified and not in site_config: should default to False
        self.manager.site_config.pop("include_media", None)
        default_manifest = self.manager.create_backup("Pre-upgrade-default")
        self.assertEqual(default_manifest["include_media"], False)
        self.assertEqual(default_manifest["backup_type"], "Partial")

    @patch("src.backup.database.DatabaseBackup.restore")
    @patch("src.backup.assets.AssetBackup.restore")
    def test_restore_backup(self, mock_asset_restore, mock_db_restore):
        # Write dummy manifest
        backup_id = "test_backup_id"
        os.makedirs(self.manager.manifests_dir, exist_ok=True)
        manifest_path = os.path.join(self.manager.manifests_dir, f"{backup_id}.json")
        
        manifest = {
            "backup_id": backup_id,
            "site_name": "test-site-slug",
            "timestamp": "2026-07-12T20:00:00Z",
            "description": "Pre-upgrade",
            "components": {
                "database": "backups/test-site-slug/db/db.sql.gz",
                "assets": "backups/test-site-slug/assets/assets.tar.gz"
            },
            "status": "completed",
            "size_bytes": 300
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)
            
        res = self.manager.restore_backup(backup_id)
        self.assertTrue(res)
        
        mock_db_restore.assert_called_once()
        mock_asset_restore.assert_called_once_with(
            os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups/test-site-slug/assets/assets.tar.gz")),
            "/var/www/wordpress"
        )

if __name__ == "__main__":
    unittest.main()
