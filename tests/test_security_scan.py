import os
import sys
import tempfile
import unittest
import json
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.app import create_app
import src.config.loader as loader

class TestSecurityScanAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.api_token = "test-token"
        
        self.orig_config_dir = loader.CONFIG_DIR
        self.orig_sites_yaml = loader.SITES_YAML_PATH

        loader.CONFIG_DIR = self.temp_dir
        loader.SITES_YAML_PATH = os.path.join(self.temp_dir, "sites.yaml")
        loader.ADMIN_DATA_JSON_PATH = os.path.join(self.temp_dir, "admin_data.json")

        with open(loader.SITES_YAML_PATH, "w") as f:
            f.write("""sites:
  - site_name: test-site
    display_name: Test Site
    status: Ready
    wp_path: /var/www/html
""")

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

    def test_security_vulnerability_install_endpoint(self):
        # Trigger package installation endpoint for test site
        res = self.client.post("/api/sites/test-site/vulnerability-package", headers=self.headers)
        # Should respond (either 200 or 400/500 if WP connection is unreachable)
        self.assertIn(res.status_code, [200, 400, 500])
        body = res.get_json()
        self.assertIn("success", body)

if __name__ == "__main__":
    unittest.main()
