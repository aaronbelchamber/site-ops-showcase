import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys
import tempfile
import shutil
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.app import create_app
from src.api.tasks import BACKGROUND_TASKS
from src.execution.base import CommandResult
from src.execution.local import LocalExecutor

class TestAPIEndToEnd(unittest.TestCase):
    def setUp(self):
        # 1. Create temporary directory for configurations
        self.temp_dir = tempfile.mkdtemp()
        self.sites_yaml = os.path.join(self.temp_dir, "sites.yaml")
        self.credentials_enc = os.path.join(self.temp_dir, "credentials.enc")
        
        # 2. Patch config paths in loader to point to temp dir
        self.yaml_patcher = patch("src.config.loader.SITES_YAML_PATH", self.sites_yaml)
        self.creds_patcher = patch("src.config.loader.CREDENTIALS_ENC_PATH", self.credentials_enc)
        self.yaml_patcher.start()
        self.creds_patcher.start()
        
        # 3. Initialize mock sites.yaml and encrypted credentials
        import dotenv
        # Ensure ENCRYPTION_KEY exists
        self.encryption_key = "test-encryption-key-must-be-32-b"
        self.env_patcher = patch.dict(os.environ, {
            "API_TOKEN": "e2e-secret-token",
            "ENCRYPTION_KEY": self.encryption_key,
            "LOG_LEVEL": "INFO"
        })
        self.env_patcher.start()
        
        # Write empty sites and credentials configs
        from src.config.loader import save_sites_config, save_credentials
        save_sites_config({})
        save_credentials({})

        # 4. Set up mock execute methods for LocalExecutor
        self.execute_patcher = patch.object(LocalExecutor, "execute", side_effect=self._mock_execute)
        self.execute_stream_patcher = patch.object(LocalExecutor, "execute_stream", side_effect=self._mock_execute_stream)
        self.execute_stream_input_patcher = patch.object(LocalExecutor, "execute_stream_input", side_effect=self._mock_execute_stream_input)
        
        self.mock_exec = self.execute_patcher.start()
        self.mock_exec_stream = self.execute_stream_patcher.start()
        self.mock_exec_stream_input = self.execute_stream_input_patcher.start()

        # 6. Set up mock for requests.get
        self.requests_patcher = patch("requests.get", side_effect=self._mock_requests_get)
        self.requests_patcher.start()

        # 5. Initialize Flask test client
        self.app = create_app()
        self.client = self.app.test_client()
        self.headers = {
            "Authorization": "Bearer e2e-secret-token",
            "Content-Type": "application/json"
        }
        
        BACKGROUND_TASKS.clear()

    def tearDown(self):
        self.yaml_patcher.stop()
        self.creds_patcher.stop()
        self.env_patcher.stop()
        self.execute_patcher.stop()
        self.execute_stream_patcher.stop()
        self.execute_stream_input_patcher.stop()
        self.requests_patcher.stop()
        
        # Clean up files created in project's logs directory
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for category in ["updates", "health", "operations"]:
            log_path = os.path.join(project_root, "logs", category, "e2e-test-site.jsonl")
            if os.path.exists(log_path):
                try:
                    os.remove(log_path)
                except Exception:
                    pass
                    
        shutil.rmtree(self.temp_dir)

    def _mock_requests_get(self, url, *args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Welcome to WordPress site content"
        return mock_resp

    def _mock_execute(self, cmd, timeout=None):
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
        if "core version" in cmd_str:
            return CommandResult(exit_code=0, stdout="6.4.2\n", stderr="", success=True)
        elif "core check-update" in cmd_str:
            return CommandResult(exit_code=0, stdout='[{"version":"6.5.0","update_type":"major","package_url":"https://example.com/wp.zip"}]\n', stderr="", success=True)
        elif "plugin list" in cmd_str:
            return CommandResult(exit_code=0, stdout='[{"name":"akismet","status":"active","update":"available","version":"5.0"},{"name":"hello","status":"inactive","update":"none","version":"1.7.2"}]\n', stderr="", success=True)
        elif "theme list" in cmd_str:
            return CommandResult(exit_code=0, stdout='[{"name":"twentytwentyfour","status":"active","update":"available","version":"1.0"},{"name":"twentytwentythree","status":"inactive","update":"none","version":"1.1"}]\n', stderr="", success=True)
        elif "db check" in cmd_str or "db query" in cmd_str:
            return CommandResult(exit_code=0, stdout="Success: Database connection OK.\n", stderr="", success=True)
        elif "cli version" in cmd_str or "wp --info" in cmd_str:
            return CommandResult(exit_code=0, stdout="WP-CLI 2.8.1\n", stderr="", success=True)
        elif "core update" in cmd_str:
            return CommandResult(exit_code=0, stdout="Success: WordPress updated to 6.5.0\n", stderr="", success=True)
        elif "plugin update" in cmd_str:
            return CommandResult(exit_code=0, stdout="Success: Plugins updated\n", stderr="", success=True)
        elif "theme update" in cmd_str:
            return CommandResult(exit_code=0, stdout="Success: Themes updated\n", stderr="", success=True)
        return CommandResult(exit_code=0, stdout="Success\n", stderr="", success=True)

    def _mock_execute_stream(self, cmd, output_path, timeout=None):
        # Simulate writing data to stream output path
        with open(output_path, "wb") as f:
            f.write(b"dummy sql or asset tar file data")
        return CommandResult(exit_code=0, stdout="Success streaming\n", stderr="", success=True)

    def _mock_execute_stream_input(self, cmd, input_path, timeout=None):
        return CommandResult(exit_code=0, stdout="Success reading stream\n", stderr="", success=True)

    def test_complete_api_e2e_flow(self):
        # 1. Verify initial sites list is empty
        response = self.client.get("/api/sites", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(len(data["data"]), 0)

        # 2. Add a new site configuration
        new_site_payload = {
            "site_name": "e2e-test-site",
            "display_name": "E2E Test Site",
            "ssh_host": "localhost",
            "wp_path": "/var/www/e2e-site",
            "db_name": "e2e_db",
            "db_user": "e2e_user",
            "db_password": "e2e_password",
            "health_check_url": "http://127.0.0.1:5000"
        }
        response = self.client.post("/api/sites", data=json.dumps(new_site_payload), headers=self.headers)
        self.assertEqual(response.status_code, 201) # Created
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["display_name"], "E2E Test Site")

        # 3. Retrieve the added site details
        response = self.client.get("/api/sites/e2e-test-site", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["wp_path"], "/var/www/e2e-site")

        # 4. Modify the site configuration
        update_payload = {
            "display_name": "E2E Test Site Updated",
            "wp_path": "/var/www/e2e-site-updated"
        }
        response = self.client.put("/api/sites/e2e-test-site", data=json.dumps(update_payload), headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["display_name"], "E2E Test Site Updated")
        self.assertEqual(data["data"]["wp_path"], "/var/www/e2e-site-updated")

        # 5. Run health checks
        response = self.client.get("/api/sites/e2e-test-site/health", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertTrue(bool(data["data"]["overall_status"]))
        self.assertEqual(data["data"]["checks"]["wp_core"]["version"], "6.4.2")

        # 6. Retrieve health check history
        response = self.client.get("/api/sites/e2e-test-site/health/history", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertGreater(len(data["data"]), 0)
        self.assertTrue(bool(data["data"][0]["overall_status"]))

        # 7. Check for updates
        response = self.client.get("/api/sites/e2e-test-site/updates?force=true", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["core"]["update_available"])
        self.assertEqual(len(data["data"]["plugins"]["plugins"]), 2)
        self.assertEqual(data["data"]["plugins"]["plugins"][0]["name"], "akismet")

        # 8. Trigger updates in background
        response = self.client.post("/api/sites/e2e-test-site/updates/core", data=json.dumps({"major": False}), headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["status"], "running")
        
        task_id = data["data"]["task_id"]
        
        # Poll task status until complete
        for _ in range(150):
            response = self.client.get(f"/api/tasks/{task_id}", headers=self.headers)
            data = json.loads(response.data)
            if data["data"]["status"] != "running":
                break
            time.sleep(0.1)
            
        self.assertEqual(data["data"]["status"], "completed")

        # 9. Trigger database & asset backup in background
        response = self.client.post("/api/sites/e2e-test-site/backups", data=json.dumps({"description": "E2E Backup"}), headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        
        backup_task_id = data["data"]["task_id"]
        
        # Poll backup task status
        for _ in range(150):
            response = self.client.get(f"/api/tasks/{backup_task_id}", headers=self.headers)
            data = json.loads(response.data)
            if data["data"]["status"] != "running":
                break
            time.sleep(0.1)
            
        self.assertEqual(data["data"]["status"], "completed")

        # 10. List backups
        response = self.client.get("/api/sites/e2e-test-site/backups", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertGreater(len(data["data"]), 0)
        descriptions = [b.get("description") for b in data["data"]]
        self.assertIn("E2E Backup", descriptions)

        # 11. Retrieve system logs and status
        response = self.client.get("/api/system/status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["status"], "online")

        response = self.client.get("/api/system/logs?limit=5", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertTrue(isinstance(data["data"]["lines"], list))

        # 12. Delete site configuration
        response = self.client.delete("/api/sites/e2e-test-site", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])

        # 13. Verify site is gone
        response = self.client.get("/api/sites", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data["data"]), 0)

if __name__ == "__main__":
    unittest.main()
