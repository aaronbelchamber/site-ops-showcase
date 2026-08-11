import os
import sys
import tempfile
import unittest
import json
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.app import create_app
import src.config.loader as loader

class TestProfilesAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.api_token = "test-token"
        
        self.orig_config_dir = loader.CONFIG_DIR
        self.orig_sites_yaml = loader.SITES_YAML_PATH
        self.orig_credentials_enc = loader.CREDENTIALS_ENC_PATH
        
        loader.CONFIG_DIR = self.temp_dir
        loader.SITES_YAML_PATH = os.path.join(self.temp_dir, "sites.yaml")
        loader.CREDENTIALS_ENC_PATH = os.path.join(self.temp_dir, "credentials.enc")
        loader.ADMIN_DATA_JSON_PATH = os.path.join(self.temp_dir, "admin_data.json")

        with open(loader.SITES_YAML_PATH, "w") as f:
            f.write("sites: []\n")

        self.env_patcher = patch.dict(os.environ, {"API_TOKEN": self.api_token})
        self.env_patcher.start()

        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()
        self.headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}

    def tearDown(self):
        self.env_patcher.stop()
        loader.CONFIG_DIR = self.orig_config_dir
        loader.SITES_YAML_PATH = self.orig_sites_yaml
        loader.CREDENTIALS_ENC_PATH = self.orig_credentials_enc

    def test_profiles_crud_lifecycle(self):
        # 1. Get empty profiles
        res = self.client.get("/api/profiles", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data, [])

        # 2. Create profile
        payload = {
            "title": "Test Production VPS",
            "ssh_host": "192.168.1.100",
            "ssh_port": 2222,
            "ssh_user": "root",
            "ssh_password": "secret_password_123",
            "ssh_private_key": "-----BEGIN RSA PRIVATE KEY-----\ntestkey\n-----END RSA PRIVATE KEY-----"
        }
        res = self.client.post("/api/profiles", headers=self.headers, data=json.dumps(payload))
        self.assertEqual(res.status_code, 200)
        created = res.get_json()["data"]
        self.assertEqual(created["title"], "Test Production VPS")
        self.assertTrue(created["has_password"])
        self.assertTrue(created["has_private_key"])
        profile_id = created["id"]

        # 3. Retrieve profiles list
        res = self.client.get("/api/profiles", headers=self.headers)
        profiles = res.get_json()["data"]
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["id"], profile_id)

        # 4. Update profile title
        payload_update = {
            "id": profile_id,
            "title": "Updated VPS Title",
            "ssh_host": "192.168.1.100",
            "ssh_port": 2222,
            "ssh_user": "root"
        }
        res = self.client.post("/api/profiles", headers=self.headers, data=json.dumps(payload_update))
        self.assertEqual(res.status_code, 200)
        updated = res.get_json()["data"]
        self.assertEqual(updated["title"], "Updated VPS Title")

        # 5. Delete profile
        res = self.client.delete(f"/api/profiles/{profile_id}", headers=self.headers)
        self.assertEqual(res.status_code, 200)

        # 6. Verify list is empty
        res = self.client.get("/api/profiles", headers=self.headers)
        self.assertEqual(res.get_json()["data"], [])

if __name__ == "__main__":
    unittest.main()
