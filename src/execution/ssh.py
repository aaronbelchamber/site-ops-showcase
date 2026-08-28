import io
import os
import socket
import paramiko
from typing import Dict, Any, Optional
from src.execution.base import BaseExecutor, CommandResult
from src.logging.logger import logger

class SSHExecutor(BaseExecutor):
    def __init__(self, host: str, port: int, user: str, credentials: Dict[str, Any]):
        self.host = host
        self.port = port
        self.user = user
        self.credentials = credentials
        self.client: Optional[paramiko.SSHClient] = None
        self.connected = False
        

    # Host keys are recorded on first connection and verified on every one
    # after (trust on first use). Bare AutoAddPolicy without a known_hosts file
    # accepted any key every time, so a machine-in-the-middle could take the
    # session and collect the credentials being presented. With the store
    # loaded, paramiko raises BadHostKeyException when a known host's key
    # changes -- the signal that actually matters.
    MANAGER_KNOWN_HOSTS = os.path.expanduser("~/.wp_site_manager/known_hosts")

    @classmethod
    def _configure_host_key_verification(cls, client: paramiko.SSHClient) -> None:
        # Honour the operator's existing trusted hosts first.
        try:
            client.load_system_host_keys()
        except Exception:
            # System host keys may not exist; this is best-effort. Continue with manager's known_hosts.
            pass

        # Then the manager's own store, which is the one new keys are written
        # to (load_host_keys sets the file paramiko saves back into).
        try:
            os.makedirs(os.path.dirname(cls.MANAGER_KNOWN_HOSTS), exist_ok=True)
            if not os.path.exists(cls.MANAGER_KNOWN_HOSTS):
                open(cls.MANAGER_KNOWN_HOSTS, "a").close()
            client.load_host_keys(cls.MANAGER_KNOWN_HOSTS)
        except Exception:
            # File may be unreadable or corrupted; this is best-effort. Bare AutoAddPolicy will record new keys.
            pass

        # SSH_STRICT_HOST_KEYS=true refuses unknown hosts outright instead of
        # recording them.
        strict = os.getenv("SSH_STRICT_HOST_KEYS", "false").strip().lower() in ("1", "true", "yes")
        client.set_missing_host_key_policy(
            paramiko.RejectPolicy() if strict else paramiko.AutoAddPolicy()
        )

    def _parse_private_key(self, key_string: str, password: Optional[str] = None) -> paramiko.PKey:
        """
        Attempt to parse a private key string using different key types.
        """
        key_classes = []
        for name in ["Ed25519Key", "RSAKey", "ECDSAKey", "DSSKey"]:
            cls = getattr(paramiko, name, None)
            if cls is not None:
                key_classes.append(cls)

        for key_class in key_classes:
            try:
                return key_class.from_private_key(io.StringIO(key_string), password=password)
            except paramiko.SSHException:
                continue
        raise ValueError("Invalid private key format or passphrase.")

    def connect(self) -> bool:
        """
        Establish connection via SSH. Reuse existing connection if healthy.
        """
        if self.connected and self.client:
            # Check if connection is active
            transport = self.client.get_transport()
            if transport and transport.is_active():
                return True
            else:
                self.disconnect()

        self.client = paramiko.SSHClient()
        self._configure_host_key_verification(self.client)
        
        pkey = None
        private_key_str = self.credentials.get("ssh_private_key")
        ssh_password = self.credentials.get("ssh_password")
        
        if private_key_str:
            private_key_str = private_key_str.strip()
            # If it is a path rather than the raw PEM key content
            if not private_key_str.startswith("-----BEGIN") and "\n" not in private_key_str:
                expanded_path = os.path.expanduser(private_key_str)
                if os.path.exists(expanded_path) and os.path.isfile(expanded_path):
                    try:
                        with open(expanded_path, "r", encoding="utf-8", errors="ignore") as f:
                            private_key_str = f.read().strip()
                    except Exception as e:
                        logger.warning(
                            f"Could not read SSH private key file '{expanded_path}' for {self.host}: {e}. "
                            f"Falling back to password/agent authentication."
                        )

            try:
                # We pass ssh_password as the passphrase to decrypt the key if encrypted
                pkey = self._parse_private_key(private_key_str, password=ssh_password)
            except Exception as e:
                logger.warning(
                    f"Could not parse the SSH private key for {self.host}: {e}. "
                    f"Falling back to password/agent authentication."
                )
                pkey = None

        try:
            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.user,
                "timeout": 15,
                "banner_timeout": 15
            }
            
            if pkey:
                connect_kwargs["pkey"] = pkey
            if ssh_password:
                connect_kwargs["password"] = ssh_password

            self.client.connect(**connect_kwargs)
            self.connected = True
            return True
        except Exception as e:
            self.disconnect()
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port} via SSH: {e}")

    def execute(self, command: str, timeout: int = 30) -> CommandResult:
        """
        Execute command on the remote server via SSH.
        Automatically connects if not already connected.
        """
        if not self.connected:
            try:
                self.connect()
            except Exception as e:
                return CommandResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"SSH Connection Failed: {e}",
                    success=False
                )
                
        if not self.client:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr="SSH Client is uninitialized.",
                success=False
            )

        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            
            # Wait for exit status
            exit_code = stdout.channel.recv_exit_status()
            
            # Read stdout and stderr
            stdout_str = stdout.read().decode('utf-8', errors='ignore')
            stderr_str = stderr.read().decode('utf-8', errors='ignore')
            
            return CommandResult(
                exit_code=exit_code,
                stdout=stdout_str,
                stderr=stderr_str,
                success=(exit_code == 0)
            )
        except socket.timeout:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds.",
                success=False
            )
        except Exception as e:
            # If transport error occurred, mark as disconnected
            transport = self.client.get_transport()
            if not transport or not transport.is_active():
                self.connected = False
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                success=False
            )

    def execute_stream(self, command: str, local_file_path: str, timeout: int = 60) -> CommandResult:
        """
        Execute command remotely and stream stdout directly into a local file.
        """
        if not self.connected:
            try:
                self.connect()
            except Exception as e:
                return CommandResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"SSH Connection Failed: {e}",
                    success=False
                )
                
        if not self.client:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr="SSH Client is uninitialized.",
                success=False
            )

        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            
            # Ensure containing directory exists
            os.makedirs(os.path.dirname(os.path.abspath(local_file_path)), exist_ok=True)
            
            with open(local_file_path, "wb") as f:
                while True:
                    chunk = stdout.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    
            exit_code = stdout.channel.recv_exit_status()
            stderr_str = stderr.read().decode('utf-8', errors='ignore')
            
            return CommandResult(
                exit_code=exit_code,
                stdout="",
                stderr=stderr_str,
                success=(exit_code == 0)
            )
        except socket.timeout:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds.",
                success=False
            )
        except Exception as e:
            # If transport error occurred, mark as disconnected
            transport = self.client.get_transport()
            if not transport or not transport.is_active():
                self.connected = False
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                success=False
            )

    def execute_stream_input(self, command: str, local_file_path: str, timeout: int = 60) -> CommandResult:
        """
        Execute command remotely and stream a local file directly into command's stdin.
        """
        if not self.connected:
            try:
                self.connect()
            except Exception as e:
                return CommandResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"SSH Connection Failed: {e}",
                    success=False
                )
                
        if not self.client:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr="SSH Client is uninitialized.",
                success=False
            )

        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            
            try:
                with open(local_file_path, "rb") as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        stdin.write(chunk)
                        stdin.flush()
            finally:
                try:
                    stdin.close()
                except Exception:
                    # Stream already closed or corrupted; best-effort cleanup. Command exit status still available.
                    pass
            
            exit_code = stdout.channel.recv_exit_status()
            stdout_str = stdout.read().decode('utf-8', errors='ignore')
            stderr_str = stderr.read().decode('utf-8', errors='ignore')
            
            return CommandResult(
                exit_code=exit_code,
                stdout=stdout_str,
                stderr=stderr_str,
                success=(exit_code == 0)
            )
        except socket.timeout:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds.",
                success=False
            )
        except Exception as e:
            # If transport error occurred, mark as disconnected
            transport = self.client.get_transport()
            if not transport or not transport.is_active():
                self.connected = False
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                success=False
            )

    @staticmethod
    def get_agent_keys() -> tuple[bool, list[str]]:
        """Query active SSH Agent keys safely."""
        agent_active = False
        agent_keys = []
        try:
            agent = paramiko.Agent()
            keys = agent.get_keys()
            if keys:
                agent_active = True
                agent_keys = [f"{k.get_name()}: {k.get_base64()[:16]}..." for k in keys]
        except Exception:
            # SSH agent not running or inaccessible; optional info for diagnostics. Return empty list.
            pass
        return agent_active, agent_keys

    @staticmethod
    def parse_ssh_config(config_path: str) -> list[dict[str, Any]]:
        """Parse ~/.ssh/config profiles into structured list."""
        profiles = []
        if os.path.exists(config_path) and os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
                    ssh_config = paramiko.SSHConfig()
                    ssh_config.parse(f)
                    for host in ssh_config.get_hostnames():
                        if host == "*":
                            continue
                        lookup = ssh_config.lookup(host)
                        profiles.append({
                            "host_alias": host,
                            "hostname": lookup.get("hostname", ""),
                            "user": lookup.get("user", ""),
                            "port": int(lookup.get("port", 22)),
                            "identity_file": lookup.get("identityfile", [""])[0] if isinstance(lookup.get("identityfile"), list) else lookup.get("identityfile", "")
                        })
            except Exception:
                # SSH config format may be invalid or entries malformed; optional profile discovery. Return what parsed ok.
                pass
        return profiles

    def disconnect(self) -> None:
        """
        Close SSH connection and reset status.
        """
        if self.client:
            try:
                self.client.close()
            except Exception:
                # Connection already closed or corrupted; best-effort cleanup. Reset state regardless.
                pass
            self.client = None
        self.connected = False
