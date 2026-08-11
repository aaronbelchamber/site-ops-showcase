from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    success: bool

class BaseExecutor(ABC):
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection if needed. Returns True if successful, False otherwise."""
        pass
    
    @abstractmethod
    def execute(self, command: str, timeout: int = 30) -> CommandResult:
        """Execute a command and return a CommandResult."""
        pass
        
    @abstractmethod
    def execute_stream(self, command: str, local_file_path: str, timeout: int = 60) -> CommandResult:
        """
        Execute command and stream stdout directly into local_file_path.
        Returns CommandResult containing exit code, empty stdout, and stderr.
        """
        pass

    @abstractmethod
    def execute_stream_input(self, command: str, local_file_path: str, timeout: int = 60) -> CommandResult:
        """
        Execute command and stream local_file_path contents directly into command's stdin.
        Returns CommandResult containing exit status, stdout, and stderr.
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close connection if needed."""
        pass

    def test_connection(self) -> bool:
        """
        Test connection by executing a simple no-op command.
        Returns True if successful, False otherwise.
        """
        try:
            if not self.connect():
                return False
            # Run simple echo to verify command execution channel is functional
            result = self.execute("echo 1", timeout=10)
            return result.success and result.stdout.strip() == "1"
        except Exception:
            return False

