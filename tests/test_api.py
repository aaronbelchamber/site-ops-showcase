import unittest
from unittest.mock import patch, MagicMock
import io
import json
import os
import sys
import time

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
    def test_get_sites_attaches_health_summary_from_snapshot(self, mock_load_config):
        mock_load_config.return_value = {
            "site-slug": {
                "display_name": "Test",
                "ssh_host": "localhost",
                "wp_path": "/var/www/html",
                "health_check_url": "http://example.com",
                "site_name": "site-slug"
            }
        }
        from src.api.routes import sites as sites_module
        with patch.object(sites_module, "PROJECT_ROOT", self.temp_dir):
            health_dir = os.path.join(self.temp_dir, "logs", "health")
            os.makedirs(health_dir, exist_ok=True)
            snapshot_path = os.path.join(health_dir, "last_snapshot_site-slug.json")
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump({
                    "id": "chk1",
                    "timestamp": "2026-08-25T00:00:00Z",
                    "overall_status": "healthy",
                    "checks": {"http": {"console_errors": [], "error_summary": {}}}
                }, f)
            sites_module._health_snapshot_cache.clear()

            headers = {"Authorization": f"Bearer {self.api_token}"}
            response = self.client.get("/api/sites", headers=headers)

        data = json.loads(response.data)
        summary = data["data"][0]["health_summary"]
        self.assertEqual(summary["id"], "chk1")
        self.assertEqual(summary["overall_status"], "healthy")

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
    @patch("src.api.routes.sites.load_sites_config")
    @patch("src.api.routes.sites.save_sites_config")
    @patch("src.api.routes.sites.save_credentials")
    def test_clone_site_success(self, mock_save_creds, mock_save_config, mock_load_config, mock_load_raw_creds):
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

        mock_executor.return_value.disconnect.assert_called_once()

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


class TestHealthSnapshotCache(unittest.TestCase):
    """
    _read_json_cached backs the health_summary GET /api/sites attaches to every
    site on every poll -- it must skip re-reading a file that hasn't changed,
    and must pick up a file that has.
    """

    def setUp(self):
        import tempfile
        from src.api.routes import sites as sites_module
        self.sites_module = sites_module
        self.temp_dir = tempfile.mkdtemp()
        self.path = os.path.join(self.temp_dir, "snapshot.json")
        self.sites_module._health_snapshot_cache.clear()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_unchanged_file_is_read_from_disk_only_once(self):
        self._write({"id": "chk1"})
        first = self.sites_module._read_json_cached(self.path)
        with patch("builtins.open") as mock_open:
            second = self.sites_module._read_json_cached(self.path)
        mock_open.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual(second, {"id": "chk1"})

    def test_changed_file_invalidates_the_cache(self):
        # Different length ensures the (mtime, size) stamp changes deterministically,
        # rather than relying on filesystem mtime resolution between fast writes.
        self._write({"id": "chk1"})
        first = self.sites_module._read_json_cached(self.path)

        self._write({"id": "chk2-updated"})
        second = self.sites_module._read_json_cached(self.path)

        self.assertEqual(first["id"], "chk1")
        self.assertEqual(second["id"], "chk2-updated")

    def test_missing_file_returns_none(self):
        result = self.sites_module._read_json_cached(os.path.join(self.temp_dir, "does-not-exist.json"))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()





class TestSPAFallbackRouting(unittest.TestCase):
    """
    Client-side routes must survive a deep link or refresh in production.

    A hand-maintained list of @app.route entries had drifted from the frontend
    router (/manage-sites and its sub-routes were never added), so those paths
    returned a JSON 404 instead of the app. The 404 handler now serves the SPA,
    which means new client routes need no server change.
    """

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.html = {"Accept": "text/html"}
        self._ensure_index_exists()

    def _ensure_index_exists(self):
        """Guarantee the one asset the fallback serves, rather than assuming it.

        `static/index.html` is build output and is gitignored, so it exists on a
        machine where the frontend has been built and nowhere else. These tests
        passed locally for exactly that reason and failed on the first clean
        checkout in CI: a hidden dependency on a previous `npm run build`, which
        is the kind of thing only a clean room finds.

        What is under test is the routing -- that a deep link reaches the SPA
        instead of a JSON 404. That holds whatever the file contains, so a
        placeholder is enough, and it is removed again afterwards so a real
        build is never left replaced by this one.
        """
        index = os.path.join(self.app.static_folder or "", "index.html")
        if os.path.exists(index):
            return
        os.makedirs(os.path.dirname(index), exist_ok=True)
        with open(index, "w", encoding="utf-8") as handle:
            handle.write("<!doctype html><title>test placeholder</title>")
        self.addCleanup(lambda: os.path.exists(index) and os.remove(index))

    def _serves_spa(self, path):
        return self.client.get(path, headers=self.html).status_code == 200

    def test_previously_broken_manage_sites_routes_serve_the_app(self):
        for path in ("/manage-sites", "/manage-sites/discovered",
                     "/manage-sites/add", "/manage-sites/configured"):
            with self.subTest(path=path):
                self.assertTrue(self._serves_spa(path), f"{path} should serve index.html")

    def test_existing_routes_still_serve_the_app(self):
        for path in ("/", "/admin", "/logs", "/profiles", "/production-health",
                     "/site/add", "/site/demo/edit", "/site/demo/details",
                     "/site/demo/health-check/abc123"):
            with self.subTest(path=path):
                self.assertTrue(self._serves_spa(path), f"{path} should serve index.html")

    def test_a_client_route_invented_later_also_works(self):
        # The point of the change: no server edit needed for a new client route.
        self.assertTrue(self._serves_spa("/some/future/client/route"))

    def test_unknown_api_paths_still_return_json_404(self):
        resp = self.client.get("/api/does-not-exist", headers=self.html)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.mimetype, "application/json")
        self.assertFalse(json.loads(resp.data)["success"])

    def test_missing_assets_still_404_rather_than_returning_html(self):
        # Returning index.html for a missing bundle would hide a build failure.
        for path in ("/assets/index-abc123.js", "/assets/style.css", "/favicon.ico"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, headers=self.html).status_code, 404)


class TestSynchronousOperationLocking(unittest.TestCase):
    """
    Endpoints that do live work inline (health check, forced update scan) must
    take the same per-site lock as the background tasks, otherwise the dashboard
    can stack concurrent SSH sessions and browser launches on one site.
    """

    def setUp(self):
        from src.api.tasks import _manager
        self.manager = _manager
        self.app = create_app()
        self.client = self.app.test_client()
        self.api_token = "test-token"
        self.env_patcher = patch.dict(os.environ, {"API_TOKEN": self.api_token})
        self.env_patcher.start()
        self.auth = {"Authorization": f"Bearer {self.api_token}"}
        self.site = {"demo": {"site_name": "demo", "status": "Ready", "display_name": "Demo",
                              "wp_path": "/var/www/html", "health_check_url": "https://example.com"}}

    def tearDown(self):
        self.env_patcher.stop()

    def test_sync_health_check_is_refused_while_site_is_busy(self):
        with patch("src.api.routes.health.load_sites_config", return_value=self.site):
            with self.manager.site_operation("demo") as acquired:
                self.assertTrue(acquired)
                resp = self.client.get("/api/sites/demo/health", headers=self.auth)
        self.assertEqual(resp.status_code, 409)
        self.assertIn("already in progress", json.loads(resp.data)["error"])

    def test_sync_health_check_releases_the_lock_afterwards(self):
        with patch("src.api.routes.health.load_sites_config", return_value=self.site), \
             patch("src.api.routes.health.HealthTaskRunner.run_health_check_task",
                   return_value={"id": "chk1", "overall_status": "healthy"}):
            first = self.client.get("/api/sites/demo/health", headers=self.auth)
            second = self.client.get("/api/sites/demo/health", headers=self.auth)
        self.assertEqual(first.status_code, 200)
        # A second call must succeed, i.e. the lock was not leaked.
        self.assertEqual(second.status_code, 200)

    def test_sync_forced_update_scan_is_refused_while_site_is_busy(self):
        with patch("src.api.routes.updates.load_sites_config", return_value=self.site):
            with self.manager.site_operation("demo") as acquired:
                self.assertTrue(acquired)
                resp = self.client.get("/api/sites/demo/updates?force=true", headers=self.auth)
        self.assertEqual(resp.status_code, 409)

    def test_lock_is_released_even_when_the_operation_raises(self):
        with patch("src.api.routes.health.load_sites_config", return_value=self.site), \
             patch("src.api.routes.health.HealthTaskRunner.run_health_check_task",
                   side_effect=RuntimeError("boom")):
            self.client.get("/api/sites/demo/health", headers=self.auth)
        # Lock must be free despite the failure.
        with self.manager.site_operation("demo") as acquired:
            self.assertTrue(acquired, "lock leaked after a failed synchronous operation")

    def test_list_users_is_refused_while_site_is_busy(self):
        with patch("src.api.routes.users.load_sites_config", return_value=self.site):
            with self.manager.site_operation("demo") as acquired:
                self.assertTrue(acquired)
                resp = self.client.get("/api/sites/demo/users", headers=self.auth)
        self.assertEqual(resp.status_code, 409)
        self.assertIn("already in progress", json.loads(resp.data)["error"])

    def test_deactivate_user_is_refused_while_site_is_busy(self):
        with patch("src.api.routes.users.load_sites_config", return_value=self.site):
            with self.manager.site_operation("demo") as acquired:
                self.assertTrue(acquired)
                resp = self.client.post("/api/sites/demo/users/5/deactivate", headers=self.auth)
        self.assertEqual(resp.status_code, 409)

    def test_deactivate_user_releases_the_lock_afterwards(self):
        with patch("src.api.routes.users.load_sites_config", return_value=self.site), \
             patch("src.api.routes.users.load_credentials", return_value={}), \
             patch("src.execution.get_executor", return_value=MagicMock()), \
             patch("src.wp.cli.WPCLI") as mock_wpcli_cls:
            mock_wpcli_cls.return_value.deactivate_user.return_value = True
            first = self.client.post("/api/sites/demo/users/5/deactivate", headers=self.auth)
        self.assertEqual(first.status_code, 200)
        # A second call must succeed, i.e. the lock was not leaked.
        with self.manager.site_operation("demo") as acquired:
            self.assertTrue(acquired, "lock leaked after a synchronous user-management operation")

    def test_scan_sites_is_refused_while_baseline_site_is_busy(self):
        import tempfile
        with patch("src.api.routes.sites.load_sites_config", return_value=self.site), \
             patch("src.config.loader.CONFIG_DIR", tempfile.mkdtemp()):
            with self.manager.site_operation("demo") as acquired:
                self.assertTrue(acquired)
                resp = self.client.post("/api/sites/scan", data=json.dumps({}), headers=self.auth)
        self.assertEqual(resp.status_code, 409)

    def test_scan_sites_releases_the_lock_afterwards(self):
        import tempfile
        with patch("src.api.routes.sites.load_sites_config", return_value=self.site), \
             patch("src.api.routes.sites.load_credentials", return_value={}), \
             patch("src.config.loader.CONFIG_DIR", tempfile.mkdtemp()), \
             patch("src.execution.get_executor", return_value=MagicMock()), \
             patch("src.wp.cli.WPCLI") as mock_wpcli_cls:
            mock_wpcli_cls.return_value.scan_server_sites.return_value = []
            first = self.client.post("/api/sites/scan", data=json.dumps({"force_rescan": True}), headers=self.auth)
        self.assertEqual(first.status_code, 200)
        with self.manager.site_operation("demo") as acquired:
            self.assertTrue(acquired, "lock leaked after scan_sites")

    def test_vulnerability_scan_is_refused_while_site_is_busy(self):
        with patch("src.api.routes.vulnerability.load_sites_config", return_value=self.site):
            with self.manager.site_operation("demo") as acquired:
                self.assertTrue(acquired)
                resp = self.client.post("/api/sites/demo/vulnerability-scan", headers=self.auth)
        self.assertEqual(resp.status_code, 409)

    def test_vulnerability_scan_releases_the_lock_afterwards(self):
        with patch("src.api.routes.vulnerability.load_sites_config", return_value=self.site), \
             patch("src.api.routes.vulnerability.load_credentials", return_value={}), \
             patch("src.api.routes.vulnerability.save_sites_config"), \
             patch("src.execution.get_executor", return_value=MagicMock()), \
             patch("src.wp.cli.WPCLI") as mock_wpcli_cls:
            mock_wpcli_cls.return_value.check_vulnerabilities.return_value = {"status": "success", "data": []}
            first = self.client.post("/api/sites/demo/vulnerability-scan", headers=self.auth)
        self.assertEqual(first.status_code, 200)
        with self.manager.site_operation("demo") as acquired:
            self.assertTrue(acquired, "lock leaked after vulnerability scan")


class TestTaskRegistryEviction(unittest.TestCase):
    """
    _tasks and _site_locks used to grow for the process lifetime -- nothing
    ever removed a finished task or a released site lock. /api/system/status
    returns the full task list, so an unbounded registry is a slow, silent
    memory leak.
    """

    def setUp(self):
        from src.api.tasks import _manager
        self.manager = _manager
        self.manager._tasks.clear()
        self.manager._task_completed_epoch.clear()
        self.manager._site_locks.clear()

    def tearDown(self):
        self.manager._tasks.clear()
        self.manager._task_completed_epoch.clear()
        self.manager._site_locks.clear()

    def test_finished_task_is_purged_after_the_retention_window(self):
        from src.api.tasks import _TASK_RETENTION_SECONDS
        tid = "old-task"
        self.manager._tasks[tid] = {"task_id": tid, "status": "completed"}
        self.manager._task_completed_epoch[tid] = time.time() - _TASK_RETENTION_SECONDS - 1

        self.assertIsNone(self.manager.get_task(tid))
        self.assertNotIn(tid, self.manager.tasks)

    def test_recently_finished_task_is_not_purged_early(self):
        tid = "fresh-task"
        self.manager._tasks[tid] = {"task_id": tid, "status": "completed"}
        self.manager._task_completed_epoch[tid] = time.time()

        self.assertIsNotNone(self.manager.get_task(tid))
        self.assertIn(tid, self.manager.tasks)

    def test_registry_is_capped_at_max_tracked_tasks(self):
        from src.api.tasks import _MAX_TRACKED_TASKS
        now = time.time()
        for i in range(_MAX_TRACKED_TASKS + 5):
            tid = f"task-{i}"
            self.manager._tasks[tid] = {"task_id": tid, "status": "completed"}
            self.manager._task_completed_epoch[tid] = now + i  # oldest-first order

        remaining = self.manager.tasks
        self.assertEqual(len(remaining), _MAX_TRACKED_TASKS)
        # The oldest-finished entries are the ones evicted, not the newest.
        self.assertNotIn("task-0", remaining)
        self.assertIn(f"task-{_MAX_TRACKED_TASKS + 4}", remaining)

    def test_running_tasks_are_never_evicted_by_the_cap(self):
        from src.api.tasks import _MAX_TRACKED_TASKS
        running_id = "still-running"
        self.manager._tasks[running_id] = {"task_id": running_id, "status": "running"}
        now = time.time()
        for i in range(_MAX_TRACKED_TASKS + 5):
            tid = f"task-{i}"
            self.manager._tasks[tid] = {"task_id": tid, "status": "completed"}
            self.manager._task_completed_epoch[tid] = now + i

        self.assertIn(running_id, self.manager.tasks)

    def test_site_lock_entry_is_dropped_once_released(self):
        with self.manager.site_operation("evict-me"):
            self.assertIn("evict-me", self.manager._site_locks)
        self.assertNotIn("evict-me", self.manager._site_locks)


class TestErrorHandlers(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.testing = False
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.client = self.app.test_client()
        self.api_token = "test-token"
        self.env_patcher = patch.dict(os.environ, {"API_TOKEN": self.api_token})
        self.env_patcher.start()
        self.auth = {"Authorization": f"Bearer {self.api_token}"}

    def tearDown(self):
        self.env_patcher.stop()

    def test_500_response_does_not_leak_exception_text(self):
        # Route handlers generally catch and self-format their own errors
        # (that duplication is tracked separately as B4); this exercises the
        # global 500 handler in app.py directly, for a truly unhandled
        # exception reaching it.
        @self.app.route("/__test_unhandled_exception")
        def _raise():
            raise RuntimeError("super secret internal detail")

        resp = self.client.get("/__test_unhandled_exception")

        self.assertEqual(resp.status_code, 500)
        data = json.loads(resp.data)
        self.assertEqual(data["error"], "Internal server error.")
        self.assertNotIn("super secret internal detail", resp.data.decode())

    def test_oversized_upload_returns_413_not_500(self):
        self.app.config["MAX_CONTENT_LENGTH"] = 1024
        oversized = b"0" * 2048

        resp = self.client.post(
            "/api/system/backups/upload",
            headers=self.auth,
            data={"file": (io.BytesIO(oversized), "backup.zip")},
            content_type="multipart/form-data",
        )

        self.assertEqual(resp.status_code, 413)
        data = json.loads(resp.data)
        self.assertFalse(data["success"])
