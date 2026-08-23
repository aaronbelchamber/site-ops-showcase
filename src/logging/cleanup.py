import os
import re
import json
import shutil
import time
import datetime
from typing import Dict, Any, List
from src.config.loader import load_sites_config, load_credentials
from src.execution import get_executor
from src.backup.manager import BackupManager
from src.logging.logger import logger, current_month_dir

MONTH_DIR_PATTERN = re.compile(r'^\d{4}-\d{2}$')
LEGACY_APP_LOG_PATTERN = re.compile(r'^app\.log(\.\d+)?$')

class CleanupManager:
    def __init__(self):
        # Calculate root paths
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.project_root = os.path.dirname(src_dir)
        self.logs_dir = os.path.join(self.project_root, "logs")

    def cleanup_old_backups(self, retention_days: int) -> int:
        """
        Orchestrate backup cleanup across all configured sites.
        """
        if retention_days < 30:
            logger.warning(f"Requested backup retention period ({retention_days} days) is less than the strict 30-day minimum. Enforcing 30 days.")
            retention_days = 30
        logger.info(f"Starting backup cleanup. Retention period: {retention_days} days.")
        try:
            sites = load_sites_config()
            credentials = load_credentials()
        except Exception as e:
            logger.error(f"Cleanup aborted: failed to load configuration: {e}")
            return 0
            
        total_deleted = 0
        for site_name, site_config in sites.items():
            executor = get_executor(site_config, credentials)
            try:
                mgr = BackupManager(site_config, credentials, executor)
                deleted = mgr.cleanup_old_backups(retention_days)
                if deleted > 0:
                    logger.info(f"Deleted {deleted} old backups for site '{site_name}'.")
                    total_deleted += deleted
            except Exception as e:
                logger.error(f"Failed to clean backups for site '{site_name}': {e}")
            finally:
                executor.disconnect()
                
        return total_deleted

    def cleanup_old_log_months(self, retention_days: int) -> int:
        """
        Delete whole logs/<YYYY-MM> directories whose month has fully aged
        past retention_days. This is how the monthly app.log self-cleans;
        the current month's directory is never touched.
        """
        if not os.path.isdir(self.logs_dir):
            return 0

        now = datetime.datetime.now(datetime.timezone.utc)
        deleted = 0

        for name in os.listdir(self.logs_dir):
            if not MONTH_DIR_PATTERN.match(name):
                continue
            path = os.path.join(self.logs_dir, name)
            if not os.path.isdir(path):
                continue
            try:
                year, month = int(name[:4]), int(name[5:7])
                # Age from the end of that month, so a month isn't deleted
                # until it's been over for the full retention window.
                if month == 12:
                    month_end = datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc)
                else:
                    month_end = datetime.datetime(year, month + 1, 1, tzinfo=datetime.timezone.utc)
                age_days = (now - month_end).days
                if age_days > retention_days:
                    shutil.rmtree(path)
                    logger.info(f"Deleted expired log month directory: logs/{name} (age: {age_days} days).")
                    deleted += 1
            except Exception as e:
                logger.error(f"Failed to evaluate/delete log month directory '{name}': {e}")

        return deleted

    def migrate_legacy_flat_logs(self, retention_days: int) -> int:
        """
        Handle the pre-monthly-organization logs/app.log[.N] files left behind
        by an upgrade: fold the live logs/app.log into the current month's
        file (so recent history isn't lost), then remove it and any rotated
        app.log.N backups once they're past the retention window.
        """
        if not os.path.isdir(self.logs_dir):
            return 0

        removed = 0
        legacy_app_log = os.path.join(self.logs_dir, "app.log")
        if os.path.isfile(legacy_app_log):
            try:
                current_log = os.path.join(current_month_dir(self.logs_dir), "app.log")
                with open(legacy_app_log, "r", encoding="utf-8", errors="ignore") as src:
                    content = src.read()
                if content:
                    with open(current_log, "a", encoding="utf-8") as dst:
                        dst.write(content)
                os.remove(legacy_app_log)
                logger.info("Migrated legacy logs/app.log into the current month's log and removed it.")
                removed += 1
            except Exception as e:
                logger.error(f"Failed to migrate legacy logs/app.log: {e}")

        now_epoch = time.time()
        retention_seconds = retention_days * 86400
        for name in os.listdir(self.logs_dir):
            if name == "app.log" or not LEGACY_APP_LOG_PATTERN.match(name):
                continue
            path = os.path.join(self.logs_dir, name)
            if not os.path.isfile(path):
                continue
            try:
                if (now_epoch - os.path.getmtime(path)) > retention_seconds:
                    os.remove(path)
                    logger.info(f"Deleted expired legacy log backup: logs/{name}")
                    removed += 1
            except Exception as e:
                logger.error(f"Failed to evaluate/delete legacy log backup '{name}': {e}")

        return removed

    def prune_app_log(self, retention_days: int) -> bool:
        """
        Prune the current month's app.log of entries older than retention_days.
        Whole expired months are removed separately by cleanup_old_log_months.
        """
        log_path = os.path.join(current_month_dir(self.logs_dir), "app.log")
        if not os.path.exists(log_path):
            return False
            
        now_epoch = time.time()
        retention_seconds = retention_days * 86400
        
        import re
        # Matches logs formatted as [YYYY-MM-DDTHH:MM:SSZ]
        ts_pattern = re.compile(r'^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\]')
        
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            pruned_lines = []
            current_entry_keep = True
            
            for line in lines:
                match = ts_pattern.match(line)
                if match:
                    ts_str = match.group(1)
                    try:
                        struct_time = time.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
                        entry_epoch = time.mktime(struct_time) - time.timezone
                        if (now_epoch - entry_epoch) <= retention_seconds:
                            current_entry_keep = True
                        else:
                            current_entry_keep = False
                    except Exception:
                        current_entry_keep = True # Keep if parsing fails
                
                if current_entry_keep:
                    pruned_lines.append(line)
            
            # Write back pruned lines
            with open(log_path, "w", encoding="utf-8") as f:
                f.writelines(pruned_lines)
                
            logger.info(f"Pruned app.log: kept {len(pruned_lines)} of {len(lines)} lines (retention: {retention_days} days).")
            return True
        except Exception as e:
            logger.error(f"Failed to prune app.log: {e}")
            return False

    def cleanup_old_logs(self, retention_days: int) -> int:
        """
        Prune old entries from JSONL logs (health, updates) and app.log that exceed the retention period.
        """
        if retention_days < 30:
            logger.warning(f"Requested log retention period ({retention_days} days) is less than the strict 30-day minimum. Enforcing 30 days.")
            retention_days = 30
        logger.info(f"Starting log pruning. Retention period: {retention_days} days.")
        
        # Prune main application log file (current month) and remove expired month directories
        self.migrate_legacy_flat_logs(retention_days)
        self.prune_app_log(retention_days)
        self.cleanup_old_log_months(retention_days)

        now_epoch = time.time()
        retention_seconds = retention_days * 86400
        
        pruned_files_count = 0
        log_dirs = [
            os.path.join(self.logs_dir, "health"),
            os.path.join(self.logs_dir, "updates")
        ]
        
        for directory in log_dirs:
            if not os.path.exists(directory):
                continue
                
            for filename in os.listdir(directory):
                if filename.endswith(".jsonl"):
                    filepath = os.path.join(directory, filename)
                    try:
                        pruned_lines = []
                        removed_count = 0
                        
                        with open(filepath, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    entry = json.loads(line)
                                    ts_str = entry.get("timestamp", "")
                                    struct_time = time.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
                                    entry_epoch = time.mktime(struct_time) - time.timezone
                                    
                                    if (now_epoch - entry_epoch) <= retention_seconds:
                                        pruned_lines.append(line)
                                    else:
                                        removed_count += 1
                                except Exception:
                                    # Keep lines that cannot be parsed to avoid data loss
                                    pruned_lines.append(line)
                                    
                        if removed_count > 0:
                            with open(filepath, "w", encoding="utf-8") as f:
                                f.write("\n".join(pruned_lines) + "\n")
                            logger.info(f"Pruned {removed_count} old entries from log: {os.path.relpath(filepath, self.project_root)}")
                            pruned_files_count += 1
                            
                    except Exception as e:
                        logger.error(f"Failed to prune log file '{filepath}': {e}")
                        
        return pruned_files_count

    def run_scheduled_cleanup(self) -> Dict[str, Any]:
        """
        Run both backup and logs cleanups.
        Uses BACKUP_RETENTION_DAYS and LOG_RETENTION_DAYS from .env as the default retention limits.
        """
        try:
            backup_retention = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
        except Exception:
            backup_retention = 30
            
        try:
            log_retention = int(os.getenv("LOG_RETENTION_DAYS", "30"))
        except Exception:
            log_retention = 30
            
        logger.info("Executing scheduled system cleanup...")
        
        deleted_backups = self.cleanup_old_backups(backup_retention)
        pruned_logs = self.cleanup_old_logs(log_retention)
        
        logger.info(f"System cleanup completed. Backups deleted: {deleted_backups}. Logs files pruned/app.log cleaned: {pruned_logs}.")
        return {
            "backup_retention_days": backup_retention,
            "log_retention_days": log_retention,
            "deleted_backups_count": deleted_backups,
            "pruned_log_files_count": pruned_logs,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

