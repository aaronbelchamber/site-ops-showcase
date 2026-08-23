import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.app import create_app
from src.api.tasks import BACKGROUND_TASKS

class TestWebAPI(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.api_token = "test-token"
        
        # Patch env variable for API_TOKEN
        self.env_patcher = patch.dict(os.environ, {"API_TOKEN": self.api_token})
        self.env_patcher.start()
        
        # Clear BACKGROUND_TASKS
        BACKGROUND_TASKS.clear()

        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir_patcher = patch("src.config.loader.CONFIG_DIR", self.temp_dir)
        self.config_dir_patcher.start()

    def tearDown(self):
        self.config_dir_patcher.stop()
        self.env_patcher.stop()
        import shutil
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_unauthorized_access(self):
        response = self.client.get("/api/sites")
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertIn("Unauthorized", data["error"])

    @patch("src.api.routes.sites.load_sites_config")
    def test_get_sites_success(self, mock_load_config):
        mock_load_config.return_value = {
            "site-slug": {
                "display_name": "Test",
                "ssh_host": "localhost",
                "wp_path": "/var/www/html",
                "health_check_url": "http://example.com",
                "site_name": "site-slug"
            }
        }
        
        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = self.client.get("/api/sites", headers=headers)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["site_name"], "site-slug")
        
        # Verify CORS headers
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    @patch("src.api.routes.sites.load_sites_config")
    @patch("src.api.routes.sites.load_credentials")
    @patch("src.api.routes.sites.save_sites_config")
    @patch("src.api.routes.sites.save_credentials")
    def test_add_site_success(self, mock_save_creds, mock_save_config, mock_load_creds, mock_load_config):
        mock_load_config.return_value = {}
        mock_load_creds.return_value = {}
        
        payload = {
            "site_name": "new-site",
            "display_name": "New Site",
            "ssh_host": "localhost",
            "wp_path": "/var/www/new",
            "db_name": "new_db",
            "db_user": "new_user",
            "db_password": "pwd",
            "health_check_url": "http://new.com"
        }
        
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        response = self.client.post("/api/sites", data=json.dumps(payload), headers=headers)
        
        self.assertEqual(response.status_code, 201) # 201 created
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        mock_save_config.assert_called_once()
        mock_save_creds.assert_called_once()

    @patch("src.api.routes.backups.load_sites_config")
    def test_create_backup_async(self, mock_load_config):
        mock_load_config.return_value = {
            "my-site": {"site_name": "my-site", "wp_path": "/var/www"}
        }
        
        # Mock run_backup_task to avoid running real logic
        with patch("src.api.routes.backups.run_backup_task") as mock_backup_task:
            mock_backup_task.return_value = {"backup_id": "test_backup"}
            headers = {"Authorization": self.api_token, "Content-Type": "application/json"}
            response = self.client.post("/api/sites/my-site/backups", data=json.dumps({"description": "test"}), headers=headers)
            
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data["success"])
            self.assertIn("task_id", data["data"])
            
            task_id = data["data"]["task_id"]
            self.assertEqual(data["data"]["status"], "running")
            
            # Check background task status endpoint
            task_response = self.client.get(f"/api/tasks/{task_id}", headers=headers)
            self.assertEqual(task_response.status_code, 200)
            task_data = json.loads(task_response.data)
            self.assertIn(task_data["data"]["status"], ["running", "completed"])

    @patch("src.api.routes.sites.load_raw_credentials")
    @patch("src.api.routes.sites.load_raw_sites_config")
    @patch("src.api.routes.sites.load_sites_config")
    @patch("src.api.routes.sites.save_sites_config")
    @patch("src.api.routes.sites.save_credentials")
    def test_clone_site_success(self, mock_save_creds, mock_save_config, mock_load_config, mock_load_raw_config, mock_load_raw_creds):
        mock_load_config.return_value = {
            "source-site": {
                "site_name": "source-site",
                "display_name": "Source Site",
                "ssh_host": "localhost",
                "wp_path": "/var/www/source",
                "db_name": "source_db",
                "db_user": "source_user",
                "health_check_url": "http://source.com"
            }
        }
        mock_load_raw_config.return_value = {
            "source-site": {
                "site_name": "source-site",
                "display_name": "Source Site",
                "ssh_host": "localhost",
                "wp_path": "/var/www/source",
                "db_name": "source_db",
                "db_user": "source_user",
                "health_check_url": "http://source.com"
            }
        }
        mock_load_raw_creds.return_value = {
            "source-site": {
                "ssh_password": "encrypted_pwd",
                "ssh_private_key": "encrypted_key",
                "db_password": "encrypted_db_pwd"
            }
        }
        
        payload = {
            "site_name": "cloned-site",
            "display_name": "Cloned Site",
            "clone_credentials_from": "source-site",
            "ssh_host": "localhost",
            "wp_path": "/var/www/cloned",
            "db_name": "cloned_db",
            "db_user": "cloned_user",
            "health_check_url": "http://cloned.com"
        }
        
        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        response = self.client.post("/api/sites", data=json.dumps(payload), headers=headers)
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        
        mock_save_creds.assert_called_once()
        saved_creds = mock_save_creds.call_args[0][0]
        self.assertIn("cloned-site", saved_creds)
        self.assertEqual(saved_creds["cloned-site"]["ssh_password"], "encrypted_pwd")
        self.assertEqual(saved_creds["cloned-site"]["ssh_private_key"], "encrypted_key")
        self.assertEqual(saved_creds["cloned-site"]["db_password"], "encrypted_db_pwd")

    @patch("src.api.routes.sites.load_sites_config")
    @patch("src.api.routes.sites.load_credentials")
    @patch("src.execution.get_executor")
    @patch("src.wp.cli.WPCLI")
    def test_scan_sites_caching(self, mock_wpcli, mock_executor, mock_creds, mock_config):
        mock_config.return_value = {
            "base-site": {"site_name": "base-site", "ssh_host": "localhost", "wp_path": "/var/www/base"}
        }
        mock_creds.return_value = {}
        mock_cli_inst = MagicMock()
        mock_cli_inst.scan_server_sites.return_value = [{"name": "Scanned Site", "wp_path": "/var/www/scanned", "url": "http://scanned.com"}]
        mock_wpcli.return_value = mock_cli_inst

        headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        
        # First scan (force rescan)
        resp1 = self.client.post("/api/sites/scan", data=json.dumps({"force_rescan": True}), headers=headers)
        if resp1.status_code != 200:
            print("RESP1 FAIL:", resp1.data.decode())
        self.assertEqual(resp1.status_code, 200)

        data1 = json.loads(resp1.data)
        self.assertTrue(data1["success"])
        self.assertFalse(data1["cached"])
        self.assertEqual(len(data1["data"]), 1)

        # Second scan (should return cached)
        resp2 = self.client.post("/api/sites/scan", data=json.dumps({"force_rescan": False}), headers=headers)
        self.assertEqual(resp2.status_code, 200)
        data2 = json.loads(resp2.data)
        self.assertTrue(data2["success"])
        self.assertTrue(data2["cached"])
        self.assertEqual(data2["data"], data1["data"])

    @patch("src.api.routes.updates.load_sites_config")
    @patch("src.api.routes.updates.load_credentials")
    @patch("src.api.routes.updates.get_executor")
    @patch("src.api.routes.updates.WPCLI")
    @patch("src.api.routes.updates.UpdateManager")
    def test_get_updates_live_scan(self, mock_mgr_class, mock_wpcli_class, mock_get_executor, mock_load_creds, mock_load_config):
        mock_load_config.return_value = {
            "systema-intel": {
                "display_name": "Systema Intel",
                "status": "Ready",
                "wp_path": "/home/pf_brandager/systemaintel.com/cms",
                "site_name": "systema-intel"
            }
        }
        mock_load_creds.return_value = {}
        mock_mgr_instance = MagicMock()
        mock_mgr_instance.check_all_updates.return_value = {
            "site_name": "systema-intel",
            "timestamp": "2026-08-08T19:00:00Z",
            "core": {"update_available": False, "details": None},
            "plugins": {"updates_available": False, "plugins": []},
            "themes": {"updates_available": False, "themes": []}
        }
        mock_mgr_class.return_value = mock_mgr_instance

        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = self.client.get("/api/sites/systema-intel/updates?force=true", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["site_name"], "systema-intel")

    @patch("src.api.routes.updates.load_sites_config")
    @patch("src.api.routes.updates.start_task")
    def test_trigger_check_updates_background(self, mock_start_task, mock_load_config):
        mock_load_config.return_value = {
            "systema-intel": {
                "display_name": "Systema Intel",
                "status": "Ready",
                "wp_path": "/home/pf_brandager/systemaintel.com/cms",
                "site_name": "systema-intel"
            }
        }
        mock_start_task.return_value = "task-12345"

        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = self.client.post("/api/sites/systema-intel/updates/check", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["task_id"], "task-12345")
        self.assertEqual(data["data"]["status"], "running")

    @patch("src.api.routes.updates.load_sites_config")
    @patch("src.api.routes.updates.start_task")
    def test_trigger_check_updates_returns_409_when_operation_in_progress(self, mock_start_task, mock_load_config):
        mock_load_config.return_value = {
            "systema-intel": {
                "display_name": "Systema Intel",
                "status": "Ready",
                "wp_path": "/home/pf_brandager/systemaintel.com/cms",
                "site_name": "systema-intel"
            }
        }
        mock_start_task.return_value = None

        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = self.client.post("/api/sites/systema-intel/updates/check", headers=headers)
        self.assertEqual(response.status_code, 409)
        data = json.loads(response.data)
        self.assertFalse(data["success"])

    @patch("src.api.routes.updates.load_sites_config")
    @patch("src.api.routes.updates.start_task")
    def test_get_updates_async_returns_409_when_operation_in_progress(self, mock_start_task, mock_load_config):
        mock_load_config.return_value = {
            "systema-intel": {
                "display_name": "Systema Intel",
                "status": "Ready",
                "wp_path": "/home/pf_brandager/systemaintel.com/cms",
                "site_name": "systema-intel"
            }
        }
        mock_start_task.return_value = None

        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = self.client.get("/api/sites/systema-intel/updates?async=true", headers=headers)
        self.assertEqual(response.status_code, 409)
        data = json.loads(response.data)
        self.assertFalse(data["success"])

    @patch("src.api.routes.updates.load_sites_config")
    def test_get_updates_missing_wp_path(self, mock_load_config):
        mock_load_config.return_value = {
            "unconfigured-site": {
                "display_name": "Unconfigured Site",
                "status": "Ready",
                "wp_path": None,
                "site_name": "unconfigured-site"
            }
        }
        headers = {"Authorization": f"Bearer {self.api_token}"}
        response = self.client.get("/api/sites/unconfigured-site/updates?force=true", headers=headers)
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertIn("wp_path", data["error"])

if __name__ == "__main__":
    unittest.main()



