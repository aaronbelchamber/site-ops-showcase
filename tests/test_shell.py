import unittest
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.local import LocalExecutor
from src.execution.shell import (
    assert_windows_shell_safe,
    is_windows_local,
    quote_path,
    quote_posix,
)

BACKSLASH = chr(92)


class TestAssertWindowsShellSafe(unittest.TestCase):
    """The reject-list is the whole defence, so it gets tested per class of input."""

    def assert_rejected(self, value, because):
        with self.assertRaises(ValueError, msg=because) as caught:
            assert_windows_shell_safe(value, "wp_path", "Site")
        return str(caught.exception)

    def test_accepts_an_ordinary_windows_path(self):
        assert_windows_shell_safe(r"C:\sites\mysite", "wp_path")

    def test_accepts_an_empty_or_missing_value(self):
        assert_windows_shell_safe("", "wp_path")
        assert_windows_shell_safe(None, "wp_path")

    def test_rejects_each_cmd_metacharacter(self):
        for char in '"&|^<>%!':
            with self.subTest(char=char):
                self.assert_rejected(f"C:{BACKSLASH}a{char}b", "cmd.exe metacharacter")

    def test_rejects_a_newline(self):
        """A newline ends the command string at that point: cmd.exe discards
        the rest rather than running it, so the command silently truncates
        instead of failing. Measured, not assumed."""
        message = self.assert_rejected("C:" + BACKSLASH + "a\nwhoami", "newline")
        self.assertIn("newline", message)

    def test_rejects_a_carriage_return(self):
        self.assertIn("carriage return",
                      self.assert_rejected("C:" + BACKSLASH + "a\rwhoami", "CR"))

    def test_rejects_the_whole_control_range(self):
        for code in (0x00, 0x07, 0x09, 0x1B, 0x1F, 0x7F):
            with self.subTest(code=code):
                self.assert_rejected(f"C:{BACKSLASH}a{chr(code)}b", "control character")

    def test_names_the_field_and_subject_so_the_message_is_actionable(self):
        message = self.assert_rejected("C:" + BACKSLASH + "a&b", "metacharacter")
        self.assertIn("Site", message)
        self.assertIn("wp_path", message)


class TestQuotePath(unittest.TestCase):
    def test_posix_quoting_handles_what_windows_rejects(self):
        """shlex.quote is safe for every one of these, so POSIX never rejects."""
        for value in ("a b", "a&b", "a\nb", "a'b", r"C:\x" + BACKSLASH):
            with self.subTest(value=value):
                quote_path(value, "wp_path", is_windows=False)

    def test_windows_wraps_in_double_quotes(self):
        self.assertEqual(quote_path(r"C:\sites\mysite", "wp_path", True),
                         '"C:' + BACKSLASH + 'sites' + BACKSLASH + 'mysite"')

    def test_windows_doubles_a_trailing_backslash(self):
        """Otherwise the backslash escapes the closing quote and the argument
        swallows the next one -- measured as a single merged argv entry."""
        self.assertEqual(quote_path("C:" + BACKSLASH + "sites" + BACKSLASH, "wp_path", True),
                         '"C:' + BACKSLASH + "sites" + BACKSLASH * 2 + '"')

    def test_windows_preserves_a_bare_drive_root(self):
        """Stripping would turn `C:\\` (the root) into `C:` (the current
        directory on that drive), which is a different location."""
        self.assertEqual(quote_path("C:" + BACKSLASH, "wp_path", True),
                         '"C:' + BACKSLASH * 2 + '"')

    def test_windows_leaves_interior_backslashes_alone(self):
        quoted = quote_path(r"C:\a\b\c", "wp_path", True)
        self.assertEqual(quoted.count(BACKSLASH), 3)

    def test_windows_rejects_before_quoting(self):
        with self.assertRaises(ValueError):
            quote_path("C:" + BACKSLASH + "a&calc.exe", "wp_path", True)


class TestQuotePosix(unittest.TestCase):
    def test_quotes_a_value_containing_a_space(self):
        self.assertEqual(quote_posix("a b"), "'a b'")

    def test_neutralises_a_command_separator(self):
        self.assertEqual(quote_posix("a; rm -rf /"), "'a; rm -rf /'")

    def test_an_empty_or_missing_value_becomes_an_empty_argument(self):
        self.assertEqual(quote_posix(""), "''")
        self.assertEqual(quote_posix(None), "''")


class TestIsWindowsLocal(unittest.TestCase):
    @patch("src.execution.shell.os.name", "nt")
    def test_true_for_local_executor_on_windows(self):
        self.assertTrue(is_windows_local(LocalExecutor()))

    @patch("src.execution.shell.os.name", "posix")
    def test_false_for_local_executor_on_posix(self):
        self.assertFalse(is_windows_local(LocalExecutor()))

    @patch("src.execution.shell.os.name", "nt")
    def test_false_for_non_local_executor_even_on_windows(self):
        self.assertFalse(is_windows_local(MagicMock()))


if __name__ == "__main__":
    unittest.main()
