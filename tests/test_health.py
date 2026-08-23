import unittest
from unittest.mock import MagicMock, patch
import os
import json
import tempfile
import shutil
import requests
import functools
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.base import CommandResult
from src.health.http_check import HTTPHealthCheck
from src.health.wp_check import WPHealthCheck
from src.health.manager import HealthCheckManager

class TestHTTPHealthCheck(unittest.TestCase):
    @patch("requests.get")
    def test_check_status_code_pass(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        checker = HTTPHealthCheck("http://example.com")
        success, code, err = checker.check_status_code(200)
        self.assertTrue(success)
        self.assertEqual(code, 200)
        self.assertIsNone(err)

    @patch("requests.get")
    def test_check_status_code_fail(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response
        
        checker = HTTPHealthCheck("http://example.com")
        success, code, err = checker.check_status_code(200)
        self.assertFalse(success)
        self.assertEqual(code, 500)

    @patch("requests.get")
    def test_check_status_code_exception(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")
        
        checker = HTTPHealthCheck("http://example.com")
        success, code, err = checker.check_status_code(200)
        self.assertFalse(success)
        self.assertEqual(code, 0)
        self.assertIn("Connection timed out", err)

    @patch("requests.get")
    def test_check_content_contains(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "Welcome to WordPress site"
        mock_get.return_value = mock_response
        
        checker = HTTPHealthCheck("http://example.com")
        success, err = checker.check_content_contains("WordPress")
        self.assertTrue(success)
        self.assertIsNone(err)

    @patch("requests.get")
    def test_verify_ssl_passed(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        # Test default is False
        checker = HTTPHealthCheck("http://example.com")
        checker.check_status_code(200)
        mock_get.assert_called_with("http://example.com", timeout=10, verify=False)
        
        # Test explicit True
        checker_secure = HTTPHealthCheck("https://example.com", verify_ssl=True)
        checker_secure.check_status_code(200)
        mock_get.assert_called_with("https://example.com", timeout=10, verify=True)

class TestHTTPHealthCheckBrowser(unittest.TestCase):
    """
    Real (non-mocked) Playwright tests for run_browser_check's broken-image /
    failed-asset-request detection. Every other health-check test mocks
    run_browser_check entirely, so this is the only coverage that actually
    exercises the browser code path added 2026-08-22.
    """

    @classmethod
    def setUpClass(cls):
        import http.server
        import threading

        cls.tmpdir = tempfile.mkdtemp()
        with open(os.path.join(cls.tmpdir, "index.html"), "w", encoding="utf-8") as f:
            f.write("""<html><body>
<h1>Test page</h1>
<img src="/broken.jpg" alt="a broken image">
<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBTAA7" alt="a working image">
</body></html>""")

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=cls.tmpdir)
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        self.screenshots_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.screenshots_dir, ignore_errors=True)

    def test_run_browser_check_detects_broken_image_and_failed_request(self):
        check = HTTPHealthCheck(f"http://127.0.0.1:{self.port}/index.html")
        result = check.run_browser_check("test-site", "test-check-1", self.screenshots_dir)

        self.assertEqual(result["status"], "fail")

        self.assertEqual(len(result["broken_images"]), 1)
        self.assertIn("broken.jpg", result["broken_images"][0]["src"])
        self.assertEqual(result["broken_images"][0]["alt"], "a broken image")

        self.assertEqual(len(result["failed_asset_requests"]), 1)
        self.assertEqual(result["failed_asset_requests"][0]["status"], 404)
        self.assertEqual(result["failed_asset_requests"][0]["resource_type"], "image")
        self.assertIn("broken.jpg", result["failed_asset_requests"][0]["url"])

    def test_run_browser_check_clean_page_has_no_asset_issues(self):
        clean_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(clean_dir, "clean.html"), "w", encoding="utf-8") as f:
                f.write("""<html><body>
<h1>Clean page</h1>
<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBTAA7" alt="fine">
</body></html>""")

            import http.server
            import threading
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=clean_dir)
            server = http.server.HTTPServer(("127.0.0.1", 0), handler)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                check = HTTPHealthCheck(f"http://127.0.0.1:{port}/clean.html")
                result = check.run_browser_check("test-site", "test-check-2", self.screenshots_dir)

                self.assertEqual(result["broken_images"], [])
                self.assertEqual(result["failed_asset_requests"], [])
                self.assertEqual(result["status"], "pass")
            finally:
                server.shutdown()
        finally:
            shutil.rmtree(clean_dir, ignore_errors=True)


class TestWPHealthCheck(unittest.TestCase):
    def setUp(self):
        self.mock_wp_cli = MagicMock()
        self.checker = WPHealthCheck(self.mock_wp_cli)

    def test_check_core_status_pass(self):
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=0, stdout="Success: Core checksums verified.", stderr="", success=True
        )
        res = self.checker.check_core_status()
        self.assertEqual(res["status"], "pass")

    def test_check_core_status_fail(self):
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=1, stdout="", stderr="Error: Checksums mismatch.", success=False
        )
        res = self.checker.check_core_status()
        self.assertEqual(res["status"], "fail")

    def test_check_core_status_fail_stdout_fallback(self):
        self.mock_wp_cli.run_command.return_value = CommandResult(
            exit_code=1, stdout="Error: Checksums mismatch in file.html", stderr="", success=False
        )
        res = self.checker.check_core_status()
        self.assertEqual(res["status"], "fail")
        self.assertIn("Error: Checksums mismatch in file.html", res["message"])

    def test_check_plugin_status(self):
        plugins_data = [
            {"name": "p1", "status": "active", "update": "none"},
            {"name": "p2", "status": "active", "update": "available"},
            {"name": "p3", "status": "inactive", "update": "none"}
        ]
        self.mock_wp_cli.list_plugins.return_value = plugins_data
        
        res = self.checker.check_plugin_status()
        self.assertEqual(res["status"], "pass")
        self.assertEqual(res["active_count"], 2)
        self.assertEqual(res["updates_available"], 1)
        self.assertEqual(res["total_count"], 3)

class TestHealthCheckManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.site_config = {
            "site_name": "test-site",
            "health_check_url": "http://example.com"
        }
        self.mock_executor = MagicMock()
        self.mock_wp_cli = MagicMock()
        
        self.manager = HealthCheckManager(self.site_config, self.mock_executor, self.mock_wp_cli)
        
        # Override log directory to temp_dir
        self.manager.health_log_dir = self.temp_dir
        self.manager.log_file = os.path.join(self.temp_dir, "test-site.jsonl")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("src.health.http_check.HTTPHealthCheck.run_browser_check")
    @patch("src.health.wp_check.WPHealthCheck.run_full_check")
    def test_run_all_checks_healthy(self, mock_wp, mock_http):
        mock_http.return_value = {
            "status_code": 200, "response_time_ms": 120, "status": "pass", "console_errors": [], "error": None
        }
        mock_wp.return_value = {
            "database_connection": "pass",
            "core_status": {"status": "pass", "message": "OK"},
            "plugins": {"status": "pass", "active_count": 5, "updates_available": 0},
            "themes": {"status": "pass", "active_theme": "twentytwentythree", "updates_available": 0},
            "status": "pass"
        }
        self.mock_wp_cli.get_core_version.return_value = "6.2"
        
        report = self.manager.run_all_checks()
        
        self.assertEqual(report["overall_status"], "healthy")
        self.assertEqual(report["checks"]["wp_core"]["version"], "6.2")
        self.assertEqual(report["checks"]["http"]["status_code"], 200)
        
        # Verify JSONL log file was written
        self.assertTrue(os.path.exists(self.manager.log_file))
        
        # Verify history
        history = self.manager.get_health_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["overall_status"], "healthy")

    @patch("src.health.http_check.HTTPHealthCheck.run_browser_check")
    @patch("src.health.wp_check.WPHealthCheck.run_full_check")
    def test_broken_image_marks_check_degraded(self, mock_wp, mock_http):
        mock_http.return_value = {
            "status_code": 200, "response_time_ms": 120, "status": "fail",
            "console_errors": [],
            "broken_images": [{"src": "https://example.com/missing.jpg", "alt": ""}],
            "failed_asset_requests": [],
            "error": None
        }
        mock_wp.return_value = {
            "database_connection": "pass",
            "core_status": {"status": "pass", "message": "OK"},
            "plugins": {"status": "pass", "active_count": 5, "updates_available": 0},
            "themes": {"status": "pass", "active_theme": "twentytwentythree", "updates_available": 0},
            "status": "pass"
        }
        self.mock_wp_cli.get_core_version.return_value = "6.2"

        report = self.manager.run_all_checks()

        self.assertEqual(report["overall_status"], "degraded")
        self.assertEqual(report["checks"]["http"]["broken_images"], [{"src": "https://example.com/missing.jpg", "alt": ""}])
        self.assertIn("broken image", " ".join(report["status_reasons"]))

    @patch("src.health.manager.HealthCheckManager.get_health_check_by_id")
    @patch("src.health.http_check.HTTPHealthCheck.run_browser_check")
    @patch("src.health.wp_check.WPHealthCheck.run_full_check")
    def test_asset_issues_matched_true_when_broken_image_preexisted(self, mock_wp, mock_http, mock_get_baseline):
        # Baseline (pre-update) already had this broken image before the update ran
        mock_get_baseline.return_value = {
            "id": "baseline-check",
            "checks": {"http": {
                "broken_images": [{"src": "https://example.com/missing.jpg", "alt": ""}],
                "failed_asset_requests": [],
                "console_errors": []
            }}
        }
        mock_http.return_value = {
            "status_code": 200, "response_time_ms": 120, "status": "fail",
            "console_errors": [],
            "broken_images": [{"src": "https://example.com/missing.jpg", "alt": ""}],
            "failed_asset_requests": [],
            "error": None
        }
        mock_wp.return_value = {
            "database_connection": "pass",
            "core_status": {"status": "pass", "message": "OK"},
            "plugins": {"status": "pass", "active_count": 5, "updates_available": 0},
            "themes": {"status": "pass", "active_theme": "twentytwentythree", "updates_available": 0},
            "status": "pass"
        }
        self.mock_wp_cli.get_core_version.return_value = "6.2"

        report = self.manager.run_all_checks(baseline_check_id="baseline-check")

        # No NEW breakage vs baseline, so the update flow shouldn't treat this as a fresh failure
        self.assertTrue(report["checks"]["http"]["asset_issues_matched"])

    @patch("src.health.manager.HealthCheckManager.get_health_check_by_id")
    @patch("src.health.http_check.HTTPHealthCheck.run_browser_check")
    @patch("src.health.wp_check.WPHealthCheck.run_full_check")
    def test_asset_issues_matched_false_when_new_breakage_appears(self, mock_wp, mock_http, mock_get_baseline):
        # Baseline (pre-update) was clean
        mock_get_baseline.return_value = {
            "id": "baseline-check",
            "checks": {"http": {"broken_images": [], "failed_asset_requests": [], "console_errors": []}}
        }
        mock_http.return_value = {
            "status_code": 200, "response_time_ms": 120, "status": "fail",
            "console_errors": [],
            "broken_images": [{"src": "https://example.com/new-broken.jpg", "alt": ""}],
            "failed_asset_requests": [],
            "error": None
        }
        mock_wp.return_value = {
            "database_connection": "pass",
            "core_status": {"status": "pass", "message": "OK"},
            "plugins": {"status": "pass", "active_count": 5, "updates_available": 0},
            "themes": {"status": "pass", "active_theme": "twentytwentythree", "updates_available": 0},
            "status": "pass"
        }
        self.mock_wp_cli.get_core_version.return_value = "6.2"

        report = self.manager.run_all_checks(baseline_check_id="baseline-check")

        self.assertFalse(report["checks"]["http"]["asset_issues_matched"])

    @patch("src.health.manager.HealthCheckManager._load_acknowledged_errors")
    @patch("src.health.http_check.HTTPHealthCheck.run_browser_check")
    @patch("src.health.wp_check.WPHealthCheck.run_full_check")
    def test_acknowledged_console_errors_persist_and_result_in_healthy_with_exception(self, mock_wp, mock_http, mock_ack):
        # Mock acknowledged error in admin_data.json (returns a list of dicts)
        mock_ack.return_value = [
            {
                "fingerprint": "a1b2c3d4",
                "acknowledged_at": "2026-08-09T00:00:00Z",
                "reason": "Known third party tracking script warning"
            }
        ]

        mock_http.return_value = {
            "status_code": 200,
            "response_time_ms": 250,
            "status": "pass",
            "console_errors": [
                {
                    "text": "Known third party tracking script warning",
                    "location": {"url": "https://example.com/tracker.js", "lineNumber": 10, "columnNumber": 5},
                    "severity": "critical",
                    "fingerprint": "a1b2c3d4"
                }
            ],
            "error": None
        }

        mock_wp.return_value = {
            "database_connection": "pass",
            "core_status": {"status": "pass", "message": "OK"},
            "plugins": {"status": "pass", "active_count": 5, "updates_available": 0},
            "themes": {"status": "pass", "active_theme": "twentytwentythree", "updates_available": 0},
            "status": "pass"
        }
        self.mock_wp_cli.get_core_version.return_value = "6.2"

        report = self.manager.run_all_checks()

        # Status must be "healthy with exception"
        self.assertEqual(report["overall_status"], "healthy with exception")
        
        # Verify the console error was tagged as acknowledged
        console_err = report["checks"]["http"]["console_errors"][0]
        self.assertEqual(console_err["severity"], "ignored")
        self.assertEqual(console_err["suppression_source"], "acknowledged")
        
        # Verify status reason reflects admin acknowledgment
        self.assertIn("Console errors acknowledged by admin", report["status_reasons"])

if __name__ == "__main__":
    unittest.main()
