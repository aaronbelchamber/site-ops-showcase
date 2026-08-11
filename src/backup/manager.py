import os
import json
import uuid
import time
from typing import Dict, Any, List, Optional

from src.backup.database import DatabaseBackup
from src.backup.assets import AssetBackup
from src.execution.base import BaseExecutor
from src.api.tasks import set_task_progress

class BackupManager:
    def __init__(self, site_config: Dict[str, Any], credentials: Dict[str, Any], executor: BaseExecutor):
        self.site_config = site_config
        self.credentials = credentials
        self.executor = executor
        self.site_name = site_config["site_name"]
        
        # Calculate backup directories relative to project root
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(src_dir)
        
        self.backups_base_dir = os.path.join(project_root, "backups", self.site_name)
        self.db_dir = os.path.join(self.backups_base_dir, "db")
        self.assets_dir = os.path.join(self.backups_base_dir, "assets")
        self.manifests_dir = os.path.join(self.backups_base_dir, "manifests")
        
        # Initialize component wrappers
        db_pass = self.credentials.get("db_password") or ""
        db_config = {
            "host": self.site_config.get("db_host", "localhost"),
            "name": self.site_config.get("db_name", ""),
            "user": self.site_config.get("db_user", ""),
            "password": db_pass
        }
        
        self.db_backup = DatabaseBackup(self.executor, db_config, self.db_dir)
        self.asset_backup = AssetBackup(
            self.executor,
            self.site_config.get("wp_path", ""),
            self.assets_dir,
            self.site_config.get("include_media", False)
        )

    def create_backup(self, description: Optional[str] = None, include_media: Optional[bool] = None, suffix: Optional[str] = None) -> Dict[str, Any]:
        """
        Orchestrate database and asset backup.
        Saves metadata to manifest JSON.
        """
        # Ensure directories exist
        os.makedirs(self.db_dir, exist_ok=True)
        os.makedirs(self.assets_dir, exist_ok=True)
        os.makedirs(self.manifests_dir, exist_ok=True)
        
        timestamp_str = time.strftime("%Y-%m-%d_%H-%M-%S")
        rand_id = uuid.uuid4().hex[:6]
        
        if suffix is None and description:
            desc_lower = description.lower()
            if "pre-core-update" in desc_lower:
                suffix = "core"
            elif "pre-plugin-update" in desc_lower:
                suffix = "plug"
            elif "pre-theme-update" in desc_lower:
                suffix = "themes"
                
        if suffix:
            clean_suffix = suffix.lstrip("-")
            if clean_suffix == "plugin":
                clean_suffix = "plug"
            elif clean_suffix == "theme":
                clean_suffix = "themes"
            backup_id = f"{self.site_name}_{timestamp_str}_{rand_id}-{clean_suffix}"
        else:
            backup_id = f"{self.site_name}_{timestamp_str}_{rand_id}"
        
        db_path = None
        asset_path = None

        include_media_val = include_media
        if include_media_val is None:
            include_media_val = self.site_config.get("include_media", False)
            
        self.asset_backup.include_media = include_media_val
        
        try:
            # 1. Database backup
            set_task_progress("Backing up remote WordPress database...")
            db_path = self.db_backup.dump()
            
            # 2. Asset backup
            set_task_progress("Archiving remote WordPress asset files...")
            asset_path = self.asset_backup.archive()
            
            # Compute sizes
            db_size = os.path.getsize(db_path) if db_path else 0
            asset_size = os.path.getsize(asset_path) if asset_path else 0
            total_size = db_size + asset_size
            
            # Relativize paths for manifest portability (relative to project root)
            src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_root = os.path.dirname(src_dir)
            
            try:
                relative_db_path = os.path.relpath(db_path, project_root).replace("\\", "/")
            except ValueError:
                relative_db_path = os.path.abspath(db_path).replace("\\", "/")
                
            try:
                relative_asset_path = os.path.relpath(asset_path, project_root).replace("\\", "/")
            except ValueError:
                relative_asset_path = os.path.abspath(asset_path).replace("\\", "/")
            
            # Create manifest
            manifest = {
                "backup_id": backup_id,
                "site_name": self.site_name,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "description": description or "Manual backup",
                "include_media": include_media_val,
                "backup_type": "Full" if include_media_val else "Partial",
                "components": {
                    "database": relative_db_path,
                    "assets": relative_asset_path
                },
                "status": "completed",
                "size_bytes": total_size
            }
            
            manifest_path = os.path.join(self.manifests_dir, f"{backup_id}.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
                
            set_task_progress("Backup completed successfully!")
            return manifest
            
        except Exception as e:
            # Cleanup any files created during failed attempt
            if db_path and os.path.exists(db_path):
                os.remove(db_path)
            if asset_path and os.path.exists(asset_path):
                os.remove(asset_path)
            raise RuntimeError(f"Backup creation failed: {e}")

    def restore_backup(self, backup_id: str) -> bool:
        """Restore both database and assets from specified backup manifest ID."""
        manifest_path = os.path.join(self.manifests_dir, f"{backup_id}.json")
        if not os.path.exists(manifest_path):
            raise FileNotFoundError(f"Backup manifest not found: {backup_id}")
            
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            
        if manifest.get("status") != "completed":
            raise ValueError(f"Cannot restore backup '{backup_id}': status is '{manifest.get('status')}'")
            
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(src_dir)
        
        # Get absolute paths to backup files
        db_relative = manifest["components"]["database"]
        asset_relative = manifest["components"]["assets"]
        
        db_abs = os.path.normpath(os.path.join(project_root, db_relative))
        asset_abs = os.path.normpath(os.path.join(project_root, asset_relative))
        
        # 1. Restore database
        set_task_progress("Restoring remote WordPress database dump...")
        self.db_backup.restore(db_abs)
        
        # 2. Restore assets
        set_task_progress("Restoring remote WordPress asset files archive...")
        self.asset_backup.restore(asset_abs, self.site_config.get("wp_path", ""))
        
        set_task_progress("Restore completed successfully!")
        return True

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all backups for this site, ordered by timestamp descending."""
        if not os.path.exists(self.manifests_dir):
            return []
            
        backups = []
        for f in os.listdir(self.manifests_dir):
            if f.endswith(".json"):
                path = os.path.join(self.manifests_dir, f)
                try:
                    with open(path, "r", encoding="utf-8") as file:
                        manifest = json.load(file)
                        # Basic schema verification
                        if "backup_id" in manifest:
                            if "backup_type" not in manifest:
                                # Infer backup_type for backward compatibility
                                if "include_media" in manifest:
                                    manifest["backup_type"] = "Full" if manifest["include_media"] else "Partial"
                                else:
                                    manifest["backup_type"] = "Full"
                            backups.append(manifest)
                except Exception:
                    pass
                    
        # Sort descending by timestamp
        backups.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return backups

    def delete_backup(self, backup_id: str) -> bool:
        """Delete files and manifest of specified backup ID."""
        manifest_path = os.path.join(self.manifests_dir, f"{backup_id}.json")
        if not os.path.exists(manifest_path):
            return False
            
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
                
            src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_root = os.path.dirname(src_dir)
            
            db_abs = os.path.normpath(os.path.join(project_root, manifest["components"]["database"]))
            asset_abs = os.path.normpath(os.path.join(project_root, manifest["components"]["assets"]))
            
            # Delete database file
            if os.path.exists(db_abs):
                os.remove(db_abs)
                
            # Delete assets file
            if os.path.exists(asset_abs):
                os.remove(asset_abs)
                
            # Delete manifest file
            os.remove(manifest_path)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to delete backup '{backup_id}': {e}")

    def cleanup_old_backups(self, retention_days: int) -> int:
        """
        Delete backups older than configured retention period.
        Returns count of deleted backups.
        """
        if retention_days < 30:
            retention_days = 30
        backups = self.list_backups()
        now_epoch = time.time()
        retention_seconds = retention_days * 86400
        
        deleted_count = 0
        for backup in backups:
            ts_str = backup.get("timestamp", "")
            try:
                # Parse ISO timestamp (e.g. 2024-01-12T14:30:00Z)
                struct_time = time.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
                backup_epoch = time.mktime(struct_time) - time.timezone
                
                if (now_epoch - backup_epoch) > retention_seconds:
                    if self.delete_backup(backup["backup_id"]):
                        deleted_count += 1
            except Exception:
                pass # skip files with unparseable timestamps
                
        return deleted_count
