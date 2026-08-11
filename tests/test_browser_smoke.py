import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import shutil
import time
import threading
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.app import create_app
from src.api.tasks import BACKGROUND_TASKS
from src.execution.base import CommandResult
from src.execution.local import LocalExecutor

class TestBrowserSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Create temporary directory for configurations
        cls.temp_dir = tempfile.mkdtemp()
        
        # 2. Setup environment variables (to be inherited by child python process)
        cls.port = 5009
        cls.api_token = "browser-secret-token"
        cls.encryption_key = "browser-test-encrypt-key-must-32"
        
        os.environ["SITE_MANAGER_CONFIG_DIR"] = cls.temp_dir
        os.environ["API_TOKEN"] = cls.api_token
        os.environ["ENCRYPTION_KEY"] = cls.encryption_key
        os.environ["LOG_LEVEL"] = "INFO"
        
        # 3. Patch config paths in loader to point to temp dir (for E2E checks in parent process if imported)
        cls.yaml_patcher = patch("src.config.loader.SITES_YAML_PATH", os.path.join(cls.temp_dir, "sites.yaml"))
        cls.creds_patcher = patch("src.config.loader.CREDENTIALS_ENC_PATH", os.path.join(cls.temp_dir, "credentials.enc"))
        cls.yaml_patcher.start()
        cls.creds_patcher.start()

        # Write empty configurations
        from src.config.loader import save_sites_config, save_credentials
        save_sites_config({})
        save_credentials({})

        # 4. Set up mock execute methods for LocalExecutor
        cls.execute_patcher = patch.object(LocalExecutor, "execute", side_effect=cls._mock_execute)
        cls.execute_stream_patcher = patch.object(LocalExecutor, "execute_stream", side_effect=cls._mock_execute_stream)
        cls.execute_stream_input_patcher = patch.object(LocalExecutor, "execute_stream_input", side_effect=cls._mock_execute_stream_input)
        cls.execute_patcher.start()
        cls.execute_stream_patcher.start()
        cls.execute_stream_input_patcher.start()

        # 5. Set up requests.get mock
        cls.requests_patcher = patch("requests.get", side_effect=cls._mock_requests_get)
        cls.requests_patcher.start()

        # 6. Launch the server in a daemon thread on custom port
        print(f"Launching Flask E2E server thread on port {cls.port}...")
        app = create_app()
        cls.server_thread = threading.Thread(
            target=app.run,
            kwargs={"host": "127.0.0.1", "port": cls.port, "debug": False, "use_reloader": False},
            daemon=True
        )
        cls.server_thread.start()
        
        # Wait for Flask to spin up on port 5009
        time.sleep(2.0)

    @classmethod
    def tearDownClass(cls):
        cls.yaml_patcher.stop()
        cls.creds_patcher.stop()
        cls.execute_patcher.stop()
        cls.execute_stream_patcher.stop()
        cls.execute_stream_input_patcher.stop()
        cls.requests_patcher.stop()

        # Clean up log files
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for category in ["updates", "health", "operations"]:
            log_path = os.path.join(project_root, "logs", category, "browser-test-site.jsonl")
            if os.path.exists(log_path):
                try:
                    os.remove(log_path)
                except Exception:
                    pass
                    
        # Remove temporary config directory
        shutil.rmtree(cls.temp_dir)

    @classmethod
    def _mock_requests_get(cls, url, *args, **kwargs):
        # Allow requests to the local server to bypass mock, otherwise mock them
        if f"127.0.0.1:{cls.port}" in url or f"localhost:{cls.port}" in url:
            # Let real request to local Flask server pass through
            import requests
            # Remove mock patch temporarily to execute real request
            with patch("requests.get", side_effect=cls._real_requests_get):
                return requests.get(url, *args, **kwargs)
                
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "Welcome to WordPress site content"
        return mock_resp

    @classmethod
    def _real_requests_get(cls, url, *args, **kwargs):
        # We need a fallback function for actual request call
        import requests
        return requests.get(url, *args, **kwargs)

    @classmethod
    def _mock_execute(cls, cmd, timeout=None):
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
        if "core version" in cmd_str:
            return CommandResult(exit_code=0, stdout="6.4.2\n", stderr="", success=True)
        elif "core check-update" in cmd_str:
            return CommandResult(exit_code=0, stdout='[{"version":"6.5.0","update_type":"major","package_url":"https://example.com/wp.zip"}]\n', stderr="", success=True)
        elif "plugin list" in cmd_str:
            return CommandResult(exit_code=0, stdout='[{"name":"akismet","status":"active","update":"available","version":"5.0"}]\n', stderr="", success=True)
        elif "theme list" in cmd_str:
            return CommandResult(exit_code=0, stdout='[{"name":"twentytwentyfour","status":"active","update":"available","version":"1.0"}]\n', stderr="", success=True)
        elif "db check" in cmd_str or "db query" in cmd_str:
            return CommandResult(exit_code=0, stdout="Success: Database connection OK.\n", stderr="", success=True)
        elif "cli version" in cmd_str or "wp --info" in cmd_str:
            return CommandResult(exit_code=0, stdout="WP-CLI 2.8.1\n", stderr="", success=True)
        return CommandResult(exit_code=0, stdout="Success\n", stderr="", success=True)

    @classmethod
    def _mock_execute_stream(cls, cmd, output_path, timeout=None):
        with open(output_path, "wb") as f:
            f.write(b"dummy stream data")
        return CommandResult(exit_code=0, stdout="Success\n", stderr="", success=True)

    @classmethod
    def _mock_execute_stream_input(cls, cmd, input_path, timeout=None):
        return CommandResult(exit_code=0, stdout="Success\n", stderr="", success=True)

    def test_browser_smoke_authentication_and_site_creation(self):
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            # 1. Launch Chromium
            headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            
            try:
                # 2. Navigate to Dashboard root
                page.goto(f"http://127.0.0.1:{self.port}/")
                
                # 3. Wait for the Authentication Overlay to be visible
                page.wait_for_selector("#authOverlay.active")
                
                # 4. Attempt login with incorrect token first
                page.fill("#tokenInput", "wrong-token")
                page.click("#authBtn")
                
                # Verify overlay remains active
                time.sleep(0.5)
                self.assertTrue(page.locator("#authOverlay").is_visible())
                
                # 5. Authenticate with correct token
                page.fill("#tokenInput", "browser-secret-token")
                page.click("#authBtn")
                
                # Verify overlay disappears
                page.wait_for_function("!document.getElementById('authOverlay').classList.contains('active')")
                
                # 6. Verify Dashboard title and empty state message
                page.wait_for_selector("#dashboardView")
                self.assertIn("WordPress Site Manager", page.title())
                
                # Wait for empty state message to appear (ensuring dashboard list has loaded)
                page.wait_for_selector("text=No sites configured yet")
                
                # 7. Add a new site configuration via page
                page.click("text=Add Your First Site")
                page.wait_for_selector("#addSiteForm")
                
                # Fill form
                page.fill("#site_name", "browser-test-site")
                page.fill("#display_name", "Browser Test Site")
                page.fill("#health_check_url", "http://example.com")
                page.fill("#wp_path", "/var/www/browser-site")
                page.fill("#db_name", "browser_db")
                page.fill("#db_user", "browser_user")
                page.fill("#db_password", "browser_pwd")
                
                # Submit form
                page.click('#addSiteForm button[type="submit"]')
                
                # Navigate back to dashboard
                page.evaluate("() => { window.history.pushState({}, '', '/'); window.dispatchEvent(new Event('popstate')); }")
                page.wait_for_selector("text=Browser Test Site")
                
                # Verify card displays correct information
                self.assertTrue(page.locator("text=browser-test-site").is_visible())
                
                # 8. Open Site Detail View
                page.click(".view-details")
                page.wait_for_selector("#detailView")
                
                # Verify site detail page displays loaded title
                page.wait_for_function("document.getElementById('detailSiteTitle') && document.getElementById('detailSiteTitle').textContent === 'Browser Test Site'")
                self.assertEqual(page.locator("#detailSiteTitle").text_content(), "Browser Test Site")
                
                # 9. Go back to dashboard
                page.click("#backToDashboardBtn")
                page.wait_for_selector("text=Browser Test Site")
                
            finally:
                browser.close()

if __name__ == "__main__":
    unittest.main()

