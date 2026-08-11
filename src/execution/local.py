import os
import subprocess
from src.execution.base import BaseExecutor, CommandResult

class LocalExecutor(BaseExecutor):
    def __init__(self):
        self.connected = True
        
    def connect(self) -> bool:
        # No-op for local
        self.connected = True
        return True
        
    def execute(self, command: str, timeout: int = 30) -> CommandResult:
        """
        Execute command locally using subprocess.
        Runs in a shell environment by default to support pipelines and redirection.
        """
        try:
            # On Windows, we use shell=True. On Linux/macOS as well.
            result = subprocess.run(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout
            )
            return CommandResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                success=(result.returncode == 0)
            )
        except subprocess.TimeoutExpired as e:
            return CommandResult(
                exit_code=-1,
                stdout=e.stdout.decode('utf-8', errors='ignore') if e.stdout else "",
                stderr=f"Command timed out after {timeout} seconds. " + (e.stderr.decode('utf-8', errors='ignore') if e.stderr else ""),
                success=False
            )
        except Exception as e:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                success=False
            )
            
    def execute_stream(self, command: str, local_file_path: str, timeout: int = 60) -> CommandResult:
        """
        Execute command locally and stream stdout directly into a local file.
        """
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Ensure containing directory exists
            os.makedirs(os.path.dirname(os.path.abspath(local_file_path)), exist_ok=True)
            
            with open(local_file_path, "wb") as f:
                while True:
                    chunk = process.stdout.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
            
            _, stderr_data = process.communicate(timeout=timeout)
            return CommandResult(
                exit_code=process.returncode,
                stdout="",
                stderr=stderr_data.decode("utf-8", errors="ignore") if stderr_data else "",
                success=(process.returncode == 0)
            )
        except subprocess.TimeoutExpired:
            process.kill()
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds.",
                success=False
            )
        except Exception as e:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                success=False
            )

    def execute_stream_input(self, command: str, local_file_path: str, timeout: int = 60) -> CommandResult:
        """
        Execute command locally and stream a local file directly into command's stdin.
        """
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            with open(local_file_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    process.stdin.write(chunk)
            process.stdin.close()
            
            stdout_data, stderr_data = process.communicate(timeout=timeout)
            return CommandResult(
                exit_code=process.returncode,
                stdout=stdout_data.decode("utf-8", errors="ignore") if stdout_data else "",
                stderr=stderr_data.decode("utf-8", errors="ignore") if stderr_data else "",
                success=(process.returncode == 0)
            )
        except subprocess.TimeoutExpired:
            process.kill()
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds.",
                success=False
            )
        except Exception as e:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                success=False
            )
            
    def start_background_process(self, command_args: list) -> subprocess.Popen:
        """Start a background process using Popen."""
        return subprocess.Popen(
            command_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=(os.name == 'nt')
        )

    def kill_port_process(self, port: int) -> None:
        """Clean up any listening process running on the specified port, excluding current process."""
        current_pid = str(os.getpid())
        parent_pid = str(os.getppid()) if hasattr(os, "getppid") else None

        if os.name == 'nt':
            res = self.execute(f'netstat -aon | findstr LISTENING | findstr :{port}')
            if res.success and res.stdout:
                for line in res.stdout.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 5 and parts[1].endswith(f':{port}'):
                        pid = parts[4]
                        if pid != current_pid and pid != parent_pid:
                            self.execute(f'taskkill /F /PID {pid}')
        else:
            res = self.execute(f'lsof -t -i:{port}')
            if res.success and res.stdout:
                for pid in res.stdout.strip().split('\n'):
                    if pid.isdigit() and pid != current_pid and pid != parent_pid:
                        self.execute(f'kill -9 {pid}')

    def disconnect(self) -> None:
        # No-op for local
        self.connected = False
