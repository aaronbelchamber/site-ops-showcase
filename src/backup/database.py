import os
import shlex
import time
from typing import Dict, Any, List
from src.execution.base import BaseExecutor

class DatabaseBackup:
    def __init__(self, executor: BaseExecutor, db_config: Dict[str, Any], local_backup_path: str):
        self.executor = executor
        self.db_config = db_config
        self.local_backup_path = local_backup_path

    def dump(self) -> str:
        """
        Create database dump and save locally using a streaming pipe.
        Returns: absolute path to created backup file.
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = self.db_config["name"]
        filename = f"{db_name}_{timestamp}.sql.gz"
        
        # Ensure target dir exists
        os.makedirs(self.local_backup_path, exist_ok=True)
        full_local_path = os.path.join(self.local_backup_path, filename)
        
        host = self.db_config.get("host", "localhost")
        user = self.db_config.get("user", "")
        password = self.db_config.get("password", "")
        
        is_windows = getattr(self.executor, "connected", False) and hasattr(self.executor, "execute") and os.name == "nt" and getattr(self.executor, "__class__", None).__name__ == "LocalExecutor"

        if is_windows:
            cmd = (
                f"set MYSQL_PWD={password}&& "
                f"mysqldump -h {shlex.quote(host)} -u {shlex.quote(user)} {shlex.quote(db_name)}"
            )
        else:
            cmd = (
                f"MYSQL_PWD={shlex.quote(password)} "
                f"mysqldump -h {shlex.quote(host)} -u {shlex.quote(user)} {shlex.quote(db_name)} | gzip"
            )
        
        res = self.executor.execute_stream(cmd, full_local_path)
        if not res.success:
            # Clean up if failed file was created
            if os.path.exists(full_local_path):
                os.remove(full_local_path)
            raise RuntimeError(f"Database dump failed: {res.stderr}")
            
        return full_local_path

    def restore(self, backup_path: str) -> bool:
        """
        Restore database from local backup file by streaming it to mysql over stdin.
        """
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
        host = self.db_config.get("host", "localhost")
        user = self.db_config.get("user", "")
        password = self.db_config.get("password", "")
        db_name = self.db_config["name"]
        
        is_windows = getattr(self.executor, "connected", False) and hasattr(self.executor, "execute") and os.name == "nt" and getattr(self.executor, "__class__", None).__name__ == "LocalExecutor"

        if is_windows:
            cmd = (
                f"set MYSQL_PWD={password}&& "
                f"mysql -h {shlex.quote(host)} -u {shlex.quote(user)} {shlex.quote(db_name)}"
            )
        else:
            cmd = (
                f"gunzip | "
                f"MYSQL_PWD={shlex.quote(password)} "
                f"mysql -h {shlex.quote(host)} -u {shlex.quote(user)} {shlex.quote(db_name)}"
            )
        
        res = self.executor.execute_stream_input(cmd, backup_path)
        if not res.success:
            raise RuntimeError(f"Database restore failed: {res.stderr}")
            
        return True

    def list_backups(self) -> List[str]:
        """List available database backups in the local directory."""
        if not os.path.exists(self.local_backup_path):
            return []
        return [
            os.path.join(self.local_backup_path, f)
            for f in os.listdir(self.local_backup_path)
            if f.endswith(".sql.gz")
        ]
