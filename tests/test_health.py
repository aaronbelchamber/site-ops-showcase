import unittest
from unittest.mock import MagicMock, patch
import os
import json
import tempfile
import shutil
import requests
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
