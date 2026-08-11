import unittest
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.config.loader as loader

class TestLoader(unittest.TestCase):
    def setUp(self):
        # We will point the loader to temporary files to avoid messing with active configuration
        self.temp_dir = tempfile.mkdtemp()
        
        # Save original paths
        self.orig_config_dir = loader.CONFIG_DIR
        self.orig_sites_yaml = loader.SITES_YAML_PATH
        self.orig_credentials_enc = loader.CREDENTIALS_ENC_PATH
        self.orig_env_path = loader.ENV_PATH
        self.orig_admin_data_json = getattr(loader, "ADMIN_DATA_JSON_PATH", None)
        
        # Override paths in loader module
        loader.CONFIG_DIR = self.temp_dir
        loader.SITES_YAML_PATH = os.path.join(self.temp_dir, "sites.yaml")
        loader.CREDENTIALS_ENC_PATH = os.path.join(self.temp_dir, "credentials.enc")
        loader.ENV_PATH = os.path.join(self.temp_dir, ".env")
        loader.ADMIN_DATA_JSON_PATH = os.path.join(self.temp_dir, "admin_data.json")
        
        # Write a dummy .env
        with open(loader.ENV_PATH, "w") as f:
            f.write("ENCRYPTION_KEY=test-master-key-32-chars-long-123\n")
        
        # Reload dotenv manually to update environment
        import dotenv
        dotenv.load_dotenv(loader.ENV_PATH, override=True)

    def tearDown(self):
        # Restore paths
        loader.CONFIG_DIR = self.orig_config_dir
        loader.SITES_YAML_PATH = self.orig_sites_yaml
        loader.CREDENTIALS_ENC_PATH = self.orig_credentials_enc
        loader.ENV_PATH = self.orig_env_path
        if self.orig_admin_data_json:
            loader.ADMIN_DATA_JSON_PATH = self.orig_admin_data_json
        
        # Clean up temp dir
        shutil.rmtree(self.temp_dir)

    def test_validate_site_name(self):
        self.assertTrue(loader.validate_site_name("my-wp-site"))
        self.assertTrue(loader.validate_site_name("wordpress123"))
        self.assertFalse(loader.validate_site_name("My-Wp-Site")) # no uppercase
        self.assertFalse(loader.validate_site_name("wp_site"))    # no underscore
        self.assertFalse(loader.validate_site_name("wp site"))    # no space
        self.assertFalse(loader.validate_site_name("-wp-site"))   # cannot start with hyphen

    def test_load_save_credentials(self):
        creds = {
            "test-site": {
                "ssh_password": "pass",
                "db_password": "db"
            }
        }
        loader.save_credentials(creds)
        self.assertTrue(os.path.exists(loader.CREDENTIALS_ENC_PATH))
        
        loaded = loader.load_credentials()
        self.assertEqual(loaded, creds)

    def test_load_save_sites_config(self):
        sites = {
            "test-site": {
                "display_name": "Test Site",
                "status": "Ready",
                "credential_profile": None,
                "ssh_host": "example.com",
                "ssh_port": 22,
                "ssh_user": "username",
                "wp_path": "/var/www/html",
                "db_host": "localhost",
                "db_name": "db",
                "db_user": "user",
                "wp_cli_path": None,
                "health_check_url": "https://example.com",
                "include_media": True,
                "site_name": "test-site",
                "source": "local",
                "domain": None
            }
        }
        loader.save_sites_config(sites)
        self.assertTrue(os.path.exists(loader.SITES_YAML_PATH))
        
        loader.save_credentials({
            "test-site": {
                "ssh_password": "pass"
            }
        })
        
        loaded = loader.load_sites_config()
        self.assertIn("test-site", loaded)
        for k, v in sites["test-site"].items():
            self.assertEqual(loaded["test-site"][k], v)

    def test_load_save_partial_in_progress(self):
        sites = {
            "partial-site": {
                "display_name": "Partial Site",
                "status": "In Progress",
                "ssh_host": None,
                "wp_path": None,
                "db_name": None,
                "db_user": None,
                "health_check_url": None
            }
        }
        loader.save_sites_config(sites)
        loaded = loader.load_sites_config()
        self.assertEqual(loaded["partial-site"]["status"], "In Progress")
        self.assertIsNone(loaded["partial-site"]["ssh_host"])

    def test_validation_invalid_url(self):
        sites = {
            "test-site": {
                "display_name": "Test Site",
                "ssh_host": "example.com",
                "wp_path": "/var/www/html",
                "db_name": "db",
                "db_user": "user",
                "health_check_url": "ftp://example.com" # invalid protocol
            }
        }
        loader.save_sites_config(sites)
        with self.assertRaises(ValueError):
            loader.load_sites_config()

    def test_get_site_domain(self):
        # Explicit domain override
        self.assertEqual(loader.get_site_domain({"domain": "custom-domain.com"}), "custom-domain.com")
        self.assertEqual(loader.get_site_domain({"domain": "  www.custom-domain.com:80  "}), "custom-domain.com")
        
        # Normalization from health check URL
        self.assertEqual(loader.get_site_domain({"health_check_url": "https://www.example.com/site1"}), "example.com")
        self.assertEqual(loader.get_site_domain({"health_check_url": "http://example.com:8080/check"}), "example.com")
        
        # Normalization from ssh_host
        self.assertEqual(loader.get_site_domain({"ssh_host": "www.host.com"}), "host.com")
        self.assertEqual(loader.get_site_domain({"ssh_host": "192.168.1.100"}), "192.168.1.100")
        
        # Empty fallbacks
        self.assertEqual(loader.get_site_domain({}), "")

    def test_load_sites_config_precedence(self):
        # Create a local sites.yaml
        local_sites = {
            "sites": {
                "local-slug": {
                    "display_name": "Local Site",
                    "status": "In Progress",
                    "health_check_url": "https://override.example.com"
                }
            }
        }
        with open(loader.SITES_YAML_PATH, "w", encoding="utf-8") as f:
            import yaml
            yaml.safe_dump(local_sites, f)
            
        # Create a versioned admin_data.json with conflicting domain name
        import json
        admin_data = {
            "sites": {
                "json-conflict": {
                    "display_name": "JSON Site Conflict",
                    "status": "In Progress",
                    "health_check_url": "https://www.override.example.com/subpath"
                },
                "json-slug-conflict": {
                    "display_name": "JSON Slug Conflict",
                    "status": "In Progress",
                    "health_check_url": "https://another-domain.com"
                },
                "json-valid": {
                    "display_name": "JSON Site Valid",
                    "status": "In Progress",
                    "health_check_url": "https://unique.com"
                }
            }
        }
        # Let's write JSON slug conflict locally to cause a slug collision
        local_sites["sites"]["json-slug-conflict"] = {
            "display_name": "Local Slug Conflict",
            "status": "In Progress",
            "health_check_url": "https://local-slug-unique.com"
        }
        with open(loader.SITES_YAML_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(local_sites, f)
            
        with open(loader.ADMIN_DATA_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(admin_data, f)
            
        loaded = loader.load_sites_config()
        
        # Verify local site takes precedence
        self.assertIn("local-slug", loaded)
        self.assertEqual(loaded["local-slug"]["display_name"], "Local Site")
        self.assertEqual(loaded["local-slug"]["source"], "local")
        
        # Verify JSON site with same domain was skipped
        self.assertNotIn("json-conflict", loaded)
        
        # Verify JSON site with same slug was skipped (local takes precedence)
        self.assertIn("json-slug-conflict", loaded)
        self.assertEqual(loaded["json-slug-conflict"]["display_name"], "Local Slug Conflict")
        self.assertEqual(loaded["json-slug-conflict"]["source"], "local")
        
        # Verify unique JSON site was loaded
        self.assertIn("json-valid", loaded)
        self.assertEqual(loaded["json-valid"]["display_name"], "JSON Site Valid")
        self.assertEqual(loaded["json-valid"]["source"], "json")

    def test_save_sites_config_selective(self):
        # Setup a combined sites dictionary
        sites = {
            "local-site": {
                "display_name": "Local Site",
                "status": "In Progress",
                "source": "local"
            },
            "json-site": {
                "display_name": "JSON Site",
                "status": "In Progress",
                "source": "json"
            }
        }
        
        # Create an existing admin_data.json with other admin data
        import json
        existing_admin = {
            "global_settings": {"test_key": "test_value"},
            "sites": {}
        }
        with open(loader.ADMIN_DATA_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(existing_admin, f)
            
        # Save config
        loader.save_sites_config(sites)
        
        # Verify local-site went to sites.yaml
        with open(loader.SITES_YAML_PATH, "r", encoding="utf-8") as f:
            import yaml
            yaml_content = yaml.safe_load(f)
            self.assertIn("local-site", yaml_content["sites"])
            self.assertNotIn("json-site", yaml_content["sites"])
            
        # Verify json-site went to admin_data.json and preserved global_settings
        with open(loader.ADMIN_DATA_JSON_PATH, "r", encoding="utf-8") as f:
            json_content = json.load(f)
            self.assertIn("json-site", json_content["sites"])
            self.assertNotIn("local-site", json_content["sites"])
            self.assertEqual(json_content["global_settings"], {"test_key": "test_value"})

    def test_admin_notes_loading_saving_migration(self):
        # 1. Test load empty when files do not exist
        if os.path.exists(loader.ADMIN_NOTES_TXT_PATH):
            os.remove(loader.ADMIN_NOTES_TXT_PATH)
        self.assertEqual(loader.load_admin_notes(), "")
        
        # 2. Test saving and loading notes
        loader.save_admin_notes("New admin notes content")
        self.assertEqual(loader.load_admin_notes(), "New admin notes content")
        
        # 3. Test migration from admin_data.json
        if os.path.exists(loader.ADMIN_NOTES_TXT_PATH):
            os.remove(loader.ADMIN_NOTES_TXT_PATH)
        
        import json
        admin_data = {
            "admin_notes": "Migrated notes content",
            "sites": {},
            "global_settings": {}
        }
        with open(loader.ADMIN_DATA_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(admin_data, f)
            
        # Trigger loader which should migrate notes
        loaded_notes = loader.load_admin_notes()
        self.assertEqual(loaded_notes, "Migrated notes content")
        
        # Verify notes file was created with the content
        self.assertTrue(os.path.exists(loader.ADMIN_NOTES_TXT_PATH))
        with open(loader.ADMIN_NOTES_TXT_PATH, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "Migrated notes content")
            
        # Verify admin_notes key was removed from admin_data.json
        with open(loader.ADMIN_DATA_JSON_PATH, "r", encoding="utf-8") as f:
            updated_admin = json.load(f)
            self.assertNotIn("admin_notes", updated_admin)

if __name__ == "__main__":
    unittest.main()
