from typing import Dict, Any, Optional
from src.execution.base import BaseExecutor, CommandResult
from src.execution.local import LocalExecutor
from src.execution.ssh import SSHExecutor

def get_executor(site_config: Optional[Dict[str, Any]] = None, credentials: Optional[Dict[str, Any]] = None) -> BaseExecutor:
    """
    Factory function to get the appropriate executor based on configuration.
    Returns LocalExecutor if host is localhost or 127.0.0.1, SSHExecutor otherwise.
    """
    site_config = site_config or {}
    credentials = credentials or {}
    host = site_config.get("ssh_host", "localhost").strip().lower()
    
    if host in ["localhost", "127.0.0.1"]:
        return LocalExecutor()
    
    port = site_config.get("ssh_port", 22)
    user = site_config.get("ssh_user", "")
    
    # Extract credentials for this site
    site_name = site_config.get("site_name")
    site_creds = credentials.get(site_name, {}) if site_name else credentials
    
    return SSHExecutor(
        host=host,
        port=port,
        user=user,
        credentials=site_creds
    )
