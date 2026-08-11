import os
import shlex
import time
from typing import List
from src.execution.base import BaseExecutor
from src.execution.local import LocalExecutor

class AssetBackup:
    def __init__(self, executor: BaseExecutor, wp_path: str, local_backup_path: str, include_media: bool):
        self.executor = executor
        self.wp_path = wp_path
        self.local_backup_path = local_backup_path
        self.include_media = include_media

    def archive(self) -> str:
        """
        Create asset archive and save locally by streaming tar stdout.
        Returns: absolute path to created backup file.
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        # Use directory name of wp_path or default to assets
        dir_name = os.path.basename(self.wp_path.rstrip("/\\")) or "assets"
        filename = f"{dir_name}_{timestamp}.tar.gz"
        
        # Ensure target dir exists
        os.makedirs(self.local_backup_path, exist_ok=True)
        full_local_path = os.path.join(self.local_backup_path, filename)
        
        # Build tar command with excludes
        # wp-content/cache is always excluded
        excludes = ["wp-content/cache", "./wp-content/cache"]
        if not self.include_media:
            excludes.extend(["wp-content/uploads", "./wp-content/uploads"])
            
        exclude_args = " ".join([f"--exclude={shlex.quote(ex)}" for ex in excludes])
        
        # We cd into the parent directory and tar the directory itself, or cd inside and tar .
        # Cding inside and tarring . is cleaner for restore.
        cmd = f"tar -czf - -C {shlex.quote(self.wp_path)} {exclude_args} ."
        
        res = self.executor.execute_stream(cmd, full_local_path)
        if not res.success:
            if os.path.exists(full_local_path):
                os.remove(full_local_path)
            raise RuntimeError(f"Asset archiving failed: {res.stderr}")
            
        return full_local_path

    def restore(self, backup_path: str, target_path: str) -> bool:
        """
        Restore assets from a local backup file with clean-slate atomic safety.
        """
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
        temp_old = f"{target_path}.old"
        is_win = isinstance(self.executor, LocalExecutor) and os.name == "nt"
        
        if is_win:
            tp = target_path.replace("\\", "/")
            to = temp_old.replace("\\", "/")
            bp = backup_path.replace("\\", "/")
            
            cmd = (
                f"powershell -Command \""
                f"if (Test-Path '{tp}') {{ "
                f"  if (Test-Path '{to}') {{ Remove-Item -Path '{to}' -Recurse -Force | Out-Null }}; "
                f"  Rename-Item -Path '{tp}' -NewName '{os.path.basename(to)}' -Force; "
                f"  New-Item -ItemType Directory -Path '{tp}' -Force | Out-Null; "
                f"  tar -xzf '{bp}' -C '{tp}'; "
                f"  if ($?) {{ Remove-Item -Path '{to}' -Recurse -Force | Out-Null }} "
                f"  else {{ Remove-Item -Path '{tp}' -Recurse -Force | Out-Null; Rename-Item -Path '{to}' -NewName '{os.path.basename(tp)}' -Force; exit 1 }}"
                f"}} else {{ "
                f"  New-Item -ItemType Directory -Path '{tp}' -Force | Out-Null; "
                f"  tar -xzf '{bp}' -C '{tp}';"
                f"}}"
                f"\""
            )
            res = self.executor.execute(cmd, timeout=300)
        else:
            tp = shlex.quote(target_path)
            to = shlex.quote(temp_old)
            
            cmd = (
                f"if [ -d {tp} ]; then "
                f"  rm -rf {to} && "
                f"  mv {tp} {to} && "
                f"  mkdir -p {tp} && "
                f"  tar -xzf - -C {tp} && "
                f"  rm -rf {to}; "
                f"  if [ $? -ne 0 ]; then rm -rf {tp} && mv {to} {tp} && exit 1; fi; "
                f"else "
                f"  mkdir -p {tp} && "
                f"  tar -xzf - -C {tp}; "
                f"fi"
            )
            res = self.executor.execute_stream_input(cmd, backup_path, timeout=300)
            
        if not res.success:
            raise RuntimeError(f"Asset restore failed: {res.stderr}")
            
        return True

    def list_backups(self) -> List[str]:
        """List available asset backups in the local directory."""
        if not os.path.exists(self.local_backup_path):
            return []
        return [
            os.path.join(self.local_backup_path, f)
            for f in os.listdir(self.local_backup_path)
            if f.endswith(".tar.gz")
        ]
