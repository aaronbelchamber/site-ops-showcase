import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.app import create_app


class TestUserManagementAPI(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.api_token = "test-token"

        self.env_patcher = patch.dict(os.environ, {"API_TOKEN": self.api_token})
        self.env_patcher.start()

        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir_patcher = patch("src.config.loader.CONFIG_DIR", self.temp_dir)
        self.config_dir_patcher.start()

        self.headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
        self.site_config = {
            "site_name": "my-site",
            "wp_path": "/var/www/my-site",
            "status": "Ready",
        }

    def tearDown(self):
        self.config_dir_patcher.stop()
        self.env_patcher.stop()
        import shutil
        if hasattr(self, "temp_dir") and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_users_requires_auth(self):
        response = self.client.get("/api/sites/my-site/users")
        self.assertEqual(response.status_code, 401)

    @patch("src.api.routes.users.load_sites_config")
    def test_list_users_site_not_found(self, mock_load_config):
        mock_load_config.return_value = {}
        response = self.client.get("/api/sites/missing-site/users", headers=self.headers)
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertFalse(data["success"])

    @patch("src.api.routes.users.load_sites_config")
    def test_list_users_site_not_ready(self, mock_load_config):
        mock_load_config.return_value = {"my-site": {**self.site_config, "status": "Pending"}}
        response = self.client.get("/api/sites/my-site/users", headers=self.headers)
        self.assertEqual(response.status_code, 400)

    @patch("src.api.routes.users.save_sites_config")
    @patch("src.wp.cli.WPCLI")
    @patch("src.execution.get_executor")
    @patch("src.api.routes.users.load_credentials")
    @patch("src.api.routes.users.load_sites_config")
    def test_list_users_success(
        self, mock_load_config, mock_load_creds, mock_get_executor, mock_wpcli_cls, mock_save_config
    ):
        mock_load_config.return_value = {"my-site": dict(self.site_config)}
        mock_load_creds.return_value = {}
        mock_cli = MagicMock()
        mock_cli.list_users.return_value = [
            {"ID": 1, "user_login": "admin", "user_email": "admin@example.com", "roles": ["administrator"]}
        ]
        mock_wpcli_cls.return_value = mock_cli

        response = self.client.get("/api/sites/my-site/users", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(len(data["data"]["users"]), 1)
        self.assertEqual(data["data"]["users"][0]["user_login"], "admin")
        self.assertIn("last_users_checked", data["data"])
        mock_save_config.assert_called_once()
        mock_get_executor.return_value.disconnect.assert_called_once()

    @patch("src.wp.cli.WPCLI")
    @patch("src.execution.get_executor")
    @patch("src.api.routes.users.load_credentials")
    @patch("src.api.routes.users.load_sites_config")
    def test_update_user_role_success(self, mock_load_config, mock_load_creds, mock_get_executor, mock_wpcli_cls):
        mock_load_config.return_value = {"my-site": dict(self.site_config)}
        mock_load_creds.return_value = {}
        mock_cli = MagicMock()
        mock_cli.update_user_role.return_value = True
        mock_wpcli_cls.return_value = mock_cli

        response = self.client.put(
            "/api/sites/my-site/users/5/role",
            data=json.dumps({"role": "editor"}),
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["role"], "editor")
        mock_cli.update_user_role.assert_called_once_with(5, "editor")
        mock_get_executor.return_value.disconnect.assert_called_once()

    @patch("src.api.routes.users.load_sites_config")
    def test_update_user_role_missing_role(self, mock_load_config):
        mock_load_config.return_value = {"my-site": dict(self.site_config)}
        response = self.client.put(
            "/api/sites/my-site/users/5/role",
            data=json.dumps({}),
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)

    @patch("src.wp.cli.WPCLI")
    @patch("src.execution.get_executor")
    @patch("src.api.routes.users.load_credentials")
    @patch("src.api.routes.users.load_sites_config")
    def test_update_user_role_failure_reported(
        self, mock_load_config, mock_load_creds, mock_get_executor, mock_wpcli_cls
    ):
        mock_load_config.return_value = {"my-site": dict(self.site_config)}
        mock_load_creds.return_value = {}
        mock_cli = MagicMock()
        mock_cli.update_user_role.return_value = False
        mock_wpcli_cls.return_value = mock_cli

        response = self.client.put(
            "/api/sites/my-site/users/5/role",
            data=json.dumps({"role": "editor"}),
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertIn("Failed to update role", data["error"])

    @patch("src.wp.cli.WPCLI")
    @patch("src.execution.get_executor")
    @patch("src.api.routes.users.load_credentials")
    @patch("src.api.routes.users.load_sites_config")
    def test_deactivate_user_success(self, mock_load_config, mock_load_creds, mock_get_executor, mock_wpcli_cls):
        mock_load_config.return_value = {"my-site": dict(self.site_config)}
        mock_load_creds.return_value = {}
        mock_cli = MagicMock()
        mock_cli.deactivate_user.return_value = True
        mock_wpcli_cls.return_value = mock_cli

        response = self.client.post("/api/sites/my-site/users/5/deactivate", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["status"], "deactivated")
        mock_cli.deactivate_user.assert_called_once_with(5)
        mock_get_executor.return_value.disconnect.assert_called_once()

    @patch("src.wp.cli.WPCLI")
    @patch("src.execution.get_executor")
    @patch("src.api.routes.users.load_credentials")
    @patch("src.api.routes.users.load_sites_config")
    def test_delete_user_success(self, mock_load_config, mock_load_creds, mock_get_executor, mock_wpcli_cls):
        mock_load_config.return_value = {"my-site": dict(self.site_config)}
        mock_load_creds.return_value = {}
        mock_cli = MagicMock()
        mock_cli.delete_user.return_value = True
        mock_wpcli_cls.return_value = mock_cli

        response = self.client.delete("/api/sites/my-site/users/5?reassign_id=1", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["deleted"])
        mock_cli.delete_user.assert_called_once_with(5, 1)
        mock_get_executor.return_value.disconnect.assert_called_once()

    @patch("src.api.routes.users.load_sites_config")
    def test_delete_user_requires_reassign_id(self, mock_load_config):
        mock_load_config.return_value = {"my-site": dict(self.site_config)}
        response = self.client.delete("/api/sites/my-site/users/5", headers=self.headers)
        self.assertEqual(response.status_code, 400)

    @patch("src.wp.cli.WPCLI")
    @patch("src.execution.get_executor")
    @patch("src.api.routes.users.load_credentials")
    @patch("src.api.routes.users.load_sites_config")
    def test_list_users_wpcli_exception_returns_500(
        self, mock_load_config, mock_load_creds, mock_get_executor, mock_wpcli_cls
    ):
        mock_load_config.return_value = {"my-site": dict(self.site_config)}
        mock_load_creds.return_value = {}
        mock_cli = MagicMock()
        mock_cli.list_users.side_effect = RuntimeError("ssh connection failed")
        mock_wpcli_cls.return_value = mock_cli

        response = self.client.get("/api/sites/my-site/users", headers=self.headers)

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertFalse(data["success"])
        self.assertIn("ssh connection failed", data["error"])
        # disconnect() must run even when the WP-CLI call raises, or the
        # SSH session leaks on every failed request.
        mock_get_executor.return_value.disconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
