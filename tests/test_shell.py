import unittest
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.local import LocalExecutor
from src.execution.shell import is_windows_local


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
