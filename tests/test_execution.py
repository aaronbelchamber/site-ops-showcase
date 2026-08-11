import unittest
from unittest.mock import MagicMock, patch
import socket
import paramiko
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.base import CommandResult
from src.execution.local import LocalExecutor
from src.execution.ssh import SSHExecutor
from src.execution import get_executor

class TestLocalExecutor(unittest.TestCase):
    def setUp(self):
        self.executor = LocalExecutor()

    def test_local_execute_success(self):
        # We can run echo command which is cross-platform enough
        result = self.executor.execute("echo Hello")
        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Hello", result.stdout)

    def test_local_execute_failure(self):
        # Non-existent command
        result = self.executor.execute("nonexistent_command_12345")
        self.assertFalse(result.success)
        self.assertNotEqual(result.exit_code, 0)

    def test_local_execute_timeout(self):
        # Run a sleep command that exceeds timeout
        # Using a timeout of 1 second
        # On Windows, timeout can be simulated by sleep or ping.
        # But we can also test it by calling execute on ping or sleep.
        # Let's run a sleep command
        result = self.executor.execute("python -c \"import time; time.sleep(5)\"", timeout=1)
        self.assertFalse(result.success)
        self.assertIn("timed out", result.stderr)

    def test_local_test_connection_success(self):
        self.assertTrue(self.executor.test_connection())

    def test_local_execute_stream(self):
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        try:
            cmd = "python -c \"import sys; sys.stdout.write('stream_output_data')\""
            result = self.executor.execute_stream(cmd, temp_path)
            self.assertTrue(result.success)
            self.assertEqual(result.exit_code, 0)
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, "stream_output_data")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_local_execute_stream_input(self):
        fd, input_path = tempfile.mkstemp()
        os.close(fd)
        with open(input_path, "w", encoding="utf-8") as f:
            f.write("stream_input_data")
            
        try:
            cmd = "python -c \"import sys; sys.stdout.write(sys.stdin.read().upper())\""
            result = self.executor.execute_stream_input(cmd, input_path)
            self.assertTrue(result.success)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout, "STREAM_INPUT_DATA")
        finally:
            if os.path.exists(input_path):
                os.remove(input_path)

class TestSSHExecutor(unittest.TestCase):
    @patch("paramiko.SSHClient")
    def test_ssh_connect_with_password(self, mock_ssh_client_class):
        mock_client = MagicMock()
        mock_ssh_client_class.return_value = mock_client
        
        credentials = {"ssh_password": "my_password"}
        executor = SSHExecutor("example.com", 22, "user", credentials)
        
        connected = executor.connect()
        self.assertTrue(connected)
        mock_client.connect.assert_called_with(
            hostname="example.com",
            port=22,
            username="user",
            password="my_password",
            timeout=15,
            banner_timeout=15
        )

    @patch("paramiko.SSHClient")
    @patch("src.execution.ssh.SSHExecutor._parse_private_key")
    def test_ssh_connect_with_pkey(self, mock_parse_key, mock_ssh_client_class):
        mock_client = MagicMock()
        mock_ssh_client_class.return_value = mock_client
        mock_pkey = MagicMock()
        mock_parse_key.return_value = mock_pkey
        
        credentials = {"ssh_private_key": "some_key_data"}
        executor = SSHExecutor("example.com", 22, "user", credentials)
        
        connected = executor.connect()
        self.assertTrue(connected)
        mock_client.connect.assert_called_with(
            hostname="example.com",
            port=22,
            username="user",
            pkey=mock_pkey,
            timeout=15,
            banner_timeout=15
        )

    @patch("paramiko.SSHClient")
    def test_ssh_execute_success(self, mock_ssh_client_class):
        mock_client = MagicMock()
        mock_ssh_client_class.return_value = mock_client
        
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.return_value = b"Command output"
        mock_stderr.read.return_value = b""
        
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
        
        executor = SSHExecutor("example.com", 22, "user", {"ssh_password": "pwd"})
        # Mock connect
        executor.connected = True
        executor.client = mock_client
        
        result = executor.execute("ls -la")
        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout.strip(), "Command output")
        mock_client.exec_command.assert_called_with("ls -la", timeout=30)

    @patch("paramiko.SSHClient")
    def test_ssh_test_connection_success(self, mock_ssh_client_class):
        mock_client = MagicMock()
        mock_ssh_client_class.return_value = mock_client
        
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.return_value = b"1\n"
        mock_stderr.read.return_value = b""
        
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
        
        executor = SSHExecutor("example.com", 22, "user", {"ssh_password": "pwd"})
        connected = executor.test_connection()
        self.assertTrue(connected)
        mock_client.connect.assert_called()
        mock_client.exec_command.assert_called_with("echo 1", timeout=10)

    @patch("paramiko.SSHClient")
    def test_ssh_test_connection_failure(self, mock_ssh_client_class):
        mock_client = MagicMock()
        mock_ssh_client_class.return_value = mock_client
        
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        
        mock_stdout.channel.recv_exit_status.return_value = 1
        mock_stdout.read.return_value = b""
        mock_stderr.read.return_value = b"error"
        
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
        
        executor = SSHExecutor("example.com", 22, "user", {"ssh_password": "pwd"})
        connected = executor.test_connection()
        self.assertFalse(connected)

    @patch("paramiko.SSHClient")
    def test_ssh_execute_stream(self, mock_ssh_client_class):
        mock_client = MagicMock()
        mock_ssh_client_class.return_value = mock_client
        
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.side_effect = [b"ssh_stream_chunk", b""]
        mock_stderr.read.return_value = b""
        
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
        
        executor = SSHExecutor("example.com", 22, "user", {"ssh_password": "pwd"})
        executor.connected = True
        executor.client = mock_client
        
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        try:
            result = executor.execute_stream("dummy_cmd", temp_path)
            self.assertTrue(result.success)
            self.assertEqual(result.exit_code, 0)
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, "ssh_stream_chunk")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @patch("paramiko.SSHClient")
    def test_ssh_execute_stream_input(self, mock_ssh_client_class):
        mock_client = MagicMock()
        mock_ssh_client_class.return_value = mock_client
        
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.return_value = b"success_output"
        mock_stderr.read.return_value = b""
        
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
        
        executor = SSHExecutor("example.com", 22, "user", {"ssh_password": "pwd"})
        executor.connected = True
        executor.client = mock_client
        
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write("input_chunk_data")
            
        try:
            result = executor.execute_stream_input("dummy_cmd", temp_path)
            self.assertTrue(result.success)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.stdout, "success_output")
            
            mock_stdin.write.assert_called_with(b"input_chunk_data")
            mock_stdin.close.assert_called_once()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

class TestExecutorFactory(unittest.TestCase):
    def test_factory_local(self):
        site_config = {"ssh_host": "localhost"}
        executor = get_executor(site_config, {})
        self.assertIsInstance(executor, LocalExecutor)
        
        site_config_ip = {"ssh_host": "127.0.0.1"}
        executor_ip = get_executor(site_config_ip, {})
        self.assertIsInstance(executor_ip, LocalExecutor)

    def test_factory_ssh(self):
        site_config = {"ssh_host": "example.com", "ssh_port": 22, "ssh_user": "user", "site_name": "my-site"}
        credentials = {"my-site": {"ssh_password": "pwd"}}
        executor = get_executor(site_config, credentials)
        self.assertIsInstance(executor, SSHExecutor)
        self.assertEqual(executor.host, "example.com")
        self.assertEqual(executor.port, 22)
        self.assertEqual(executor.user, "user")

if __name__ == "__main__":
    unittest.main()
