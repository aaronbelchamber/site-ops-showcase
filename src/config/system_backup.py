import os
import shutil
import zipfile
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from src.config.loader import SITES_YAML_PATH, ADMIN_DATA_JSON_PATH, CREDENTIALS_ENC_PATH, ADMIN_NOTES_TXT_PATH

_BACKUP_README = """WordPress Site Manager - configuration backup
=============================================

This archive contains:
  sites.yaml        site definitions (local)
  admin_data.json   site definitions (versioned)
  admin_notes.txt   operator notes
  credentials.enc   SSH passwords / private keys, ENCRYPTED

It deliberately does NOT contain config/.env.

.env holds ENCRYPTION_KEY, which is the passphrase for credentials.enc. Shipping
both in one archive would mean anyone holding this file could decrypt every
stored SSH credential, so the key is excluded and the archive is only as
sensitive as the encryption protecting it.

To restore onto a new machine you need BOTH this archive and the original
ENCRYPTION_KEY. Back that key up separately, in a password manager or secret
store -- without it, credentials.enc cannot be decrypted.

Restoring this archive does not modify .env on the target install.
"""

class SystemBackupManager:
    @classmethod
    def get_backup_dir(cls) -> Path:
        """Retrieve and ensure the system backups directory path."""
        src_directory = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        backup_directory = Path(src_directory) / "backups" / "system"
        backup_directory.mkdir(parents=True, exist_ok=True)
        return backup_directory

    @classmethod
    def get_gdrive_dir(cls) -> Optional[Path]:
        """Retrieve Google Drive backup directory from environment if configured and valid."""
        gdrive_path_str = os.getenv("GOOGLE_DRIVE_BACKUP_PATH")
        if not gdrive_path_str:
            return None
        gdrive_path = Path(gdrive_path_str)
        try:
            gdrive_path.mkdir(parents=True, exist_ok=True)
            return gdrive_path
        except Exception:
            return None

    @classmethod
    def verify_gdrive_path(cls, gdrive_path_str: str) -> Dict[str, Any]:
        """Verify that a candidate Google Drive directory exists and is writable."""
        target_path = Path(gdrive_path_str)
        try:
            target_path.mkdir(parents=True, exist_ok=True)
            test_file = target_path / ".wp_manager_sync_test.tmp"
            test_file.write_text("verification_token_ok")
            test_content = test_file.read_text()
            test_file.unlink()
            if test_content == "verification_token_ok":
                return {"valid": True, "path": str(target_path), "message": "Google Drive folder verified and writable."}
            return {"valid": False, "path": str(target_path), "message": "Test verification token mismatch."}
        except Exception as err:
            return {"valid": False, "path": str(target_path), "message": f"Write permission failed: {str(err)}"}

    @classmethod
    def create_backup(cls) -> str:
        """Create a timestamped zip backup of sites.yaml, admin_data.json, .env, and credentials.enc.
        Automatically copies the archive to Google Drive if configured.
        
        Returns:
            str: Absolute path to the created ZIP file.
        """
        backup_directory = cls.get_backup_dir()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        zip_filename = f"system_backup_{timestamp}.zip"
        zip_file_path = backup_directory / zip_filename

        with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            if os.path.exists(SITES_YAML_PATH):
                zip_file.write(SITES_YAML_PATH, "sites.yaml")
            if os.path.exists(ADMIN_DATA_JSON_PATH):
                zip_file.write(ADMIN_DATA_JSON_PATH, "admin_data.json")
            if os.path.exists(CREDENTIALS_ENC_PATH):
                zip_file.write(CREDENTIALS_ENC_PATH, "credentials.enc")
            if os.path.exists(ADMIN_NOTES_TXT_PATH):
                zip_file.write(ADMIN_NOTES_TXT_PATH, "admin_notes.txt")
            zip_file.writestr("README.txt", _BACKUP_README)

        # Sync to Google Drive if configured
        gdrive_dir = cls.get_gdrive_dir()
        if gdrive_dir:
            try:
                gdrive_target = gdrive_dir / zip_filename
                shutil.copy2(zip_file_path, gdrive_target)
            except Exception as sync_err:
                # Google Drive sync is best-effort. Local backup remains in backups/system regardless.
                pass

        return str(zip_file_path)

    @classmethod
    def list_backups(cls) -> List[Dict[str, Any]]:
        """List all available system backups on disk with metadata.
        
        Returns:
            List[Dict[str, Any]]: List of backups sorted descending by creation date.
        """
        backup_directory = cls.get_backup_dir()
        backups_list = []
        for file_path in backup_directory.glob("system_backup_*.zip"):
            file_stats = file_path.stat()
            backups_list.append({
                "filename": file_path.name,
                "size_bytes": file_stats.st_size,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(file_stats.st_mtime))
            })
        # Sort by creation time descending
        backups_list.sort(key=lambda x: x["created_at"], reverse=True)
        return backups_list

    @classmethod
    def restore_backup(cls, filename: str) -> None:
        """Restore configuration settings from a specific backup file.
        
        Args:
            filename (str): The filename of the backup zip file to restore.
        """
        backup_directory = cls.get_backup_dir()
        zip_file_path = backup_directory / filename
        if not zip_file_path.exists():
            raise FileNotFoundError(f"Backup file '{filename}' does not exist.")

        # Create temporary directory to extract and validate
        temporary_extraction_directory = backup_directory / "temp_extract"
        if temporary_extraction_directory.exists():
            shutil.rmtree(temporary_extraction_directory)
        temporary_extraction_directory.mkdir()

        try:
            with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
                zip_file.extractall(temporary_extraction_directory)

            # Define temporary file locations. `.env` is deliberately absent:
            # restoring it would overwrite API_TOKEN / ENCRYPTION_KEY on this
            # install (locking the operator out, or silently orphaning
            # credentials.enc). Legacy archives may still contain one; it is
            # extracted to the temp dir and discarded with it.
            temp_yaml = temporary_extraction_directory / "sites.yaml"
            temp_json = temporary_extraction_directory / "admin_data.json"
            temp_enc = temporary_extraction_directory / "credentials.enc"
            temp_notes = temporary_extraction_directory / "admin_notes.txt"

            # Create backup copies of current files first in case of rollback needs
            if os.path.exists(SITES_YAML_PATH):
                shutil.copy2(SITES_YAML_PATH, SITES_YAML_PATH + ".bak")
            if os.path.exists(ADMIN_DATA_JSON_PATH):
                shutil.copy2(ADMIN_DATA_JSON_PATH, ADMIN_DATA_JSON_PATH + ".bak")
            if os.path.exists(CREDENTIALS_ENC_PATH):
                shutil.copy2(CREDENTIALS_ENC_PATH, CREDENTIALS_ENC_PATH + ".bak")
            if os.path.exists(ADMIN_NOTES_TXT_PATH):
                shutil.copy2(ADMIN_NOTES_TXT_PATH, ADMIN_NOTES_TXT_PATH + ".bak")

            # Restore sites.yaml
            if temp_yaml.exists():
                os.makedirs(os.path.dirname(SITES_YAML_PATH), exist_ok=True)
                shutil.copy2(temp_yaml, SITES_YAML_PATH)
            # Restore admin_data.json
            if temp_json.exists():
                os.makedirs(os.path.dirname(ADMIN_DATA_JSON_PATH), exist_ok=True)
                shutil.copy2(temp_json, ADMIN_DATA_JSON_PATH)
            # Restore credentials.enc
            if temp_enc.exists():
                os.makedirs(os.path.dirname(CREDENTIALS_ENC_PATH), exist_ok=True)
                shutil.copy2(temp_enc, CREDENTIALS_ENC_PATH)
            # Restore admin_notes.txt
            if temp_notes.exists():
                os.makedirs(os.path.dirname(ADMIN_NOTES_TXT_PATH), exist_ok=True)
                shutil.copy2(temp_notes, ADMIN_NOTES_TXT_PATH)
        finally:
            if temporary_extraction_directory.exists():
                shutil.rmtree(temporary_extraction_directory)

    @classmethod
    def delete_backup(cls, filename: str) -> None:
        """Delete a specific backup file from the backup folder.
        
        Args:
            filename (str): The filename of the backup file to delete.
        """
        backup_directory = cls.get_backup_dir()
        zip_file_path = backup_directory / filename
        if zip_file_path.exists():
            zip_file_path.unlink()
