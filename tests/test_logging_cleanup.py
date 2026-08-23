import unittest
from unittest.mock import MagicMock, patch
import os
import json
import tempfile
import shutil
import time
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.logging.logger import logger
from src.logging.cleanup import CleanupManager

class TestLoggingAndCleanup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
        # Override project directories in cleanup manager
        self.cleanup_mgr = CleanupManager()
        self.cleanup_mgr.project_root = self.temp_dir
        self.cleanup_mgr.logs_dir = os.path.join(self.temp_dir, "logs")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_logger_writes_to_file(self):
        # We can use the global logger to check it works
        logger.info("Test log statement")

        # Verify app.log file exists in the current month's logs subdirectory
        from src.logging.logger import current_month_dir
        log_file = os.path.join(current_month_dir(), "app.log")

        self.assertTrue(os.path.exists(log_file))
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Test log statement", content)

    def test_cleanup_deletes_expired_month_directories(self):
        import datetime
        # A month directory old enough to be past the 30-day minimum retention
        old_month = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=95)).strftime("%Y-%m")
        old_dir = os.path.join(self.cleanup_mgr.logs_dir, old_month)
        os.makedirs(old_dir, exist_ok=True)
        with open(os.path.join(old_dir, "app.log"), "w", encoding="utf-8") as f:
            f.write("old entry\n")

        deleted = self.cleanup_mgr.cleanup_old_log_months(retention_days=30)

        self.assertEqual(deleted, 1)
        self.assertFalse(os.path.exists(old_dir))

    def test_cleanup_logs_pruning(self):
        health_dir = os.path.join(self.cleanup_mgr.logs_dir, "health")
        os.makedirs(health_dir, exist_ok=True)
        log_file = os.path.join(health_dir, "test-site.jsonl")
        
        # Write dummy health logs (some old, some recent)
        # We will request retention of 5 days. Because of 30-day minimum, it will enforce 30 days.
        now_epoch = time.time()
        
        # 40 days ago (should be deleted)
        old_time_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch - 40 * 86400))
        # 10 days ago (should be kept because 10 days < 30 days minimum)
        mid_time_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch - 10 * 86400))
        # 2 days ago (should be kept)
        recent_time_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch - 2 * 86400))
        
        old_entry = {"timestamp": old_time_str, "status": "healthy", "site_name": "test-site"}
        mid_entry = {"timestamp": mid_time_str, "status": "healthy", "site_name": "test-site"}
        recent_entry = {"timestamp": recent_time_str, "status": "healthy", "site_name": "test-site"}
        
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(old_entry) + "\n")
            f.write(json.dumps(mid_entry) + "\n")
            f.write(json.dumps(recent_entry) + "\n")
            
        # Run log pruning with requested retention of 5 days (internally raises to 30)
        pruned_files = self.cleanup_mgr.cleanup_old_logs(retention_days=5)
        
        self.assertEqual(pruned_files, 1)
        
        # Verify only the mid and recent entries remain in the log file
        with open(log_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            
        self.assertEqual(len(lines), 2)
        remaining_1 = json.loads(lines[0])
        remaining_2 = json.loads(lines[1])
        self.assertEqual(remaining_1["timestamp"], mid_time_str)
        self.assertEqual(remaining_2["timestamp"], recent_time_str)

    def test_migrate_legacy_flat_logs(self):
        os.makedirs(self.cleanup_mgr.logs_dir, exist_ok=True)
        legacy_log = os.path.join(self.cleanup_mgr.logs_dir, "app.log")
        with open(legacy_log, "w", encoding="utf-8") as f:
            f.write("[2020-01-01T00:00:00Z] [INFO] legacy entry\n")

        # A rotated backup old enough to be past the 30-day minimum retention
        old_backup = os.path.join(self.cleanup_mgr.logs_dir, "app.log.1")
        with open(old_backup, "w", encoding="utf-8") as f:
            f.write("old rotated entry\n")
        old_time = time.time() - 40 * 86400
        os.utime(old_backup, (old_time, old_time))

        migrated = self.cleanup_mgr.migrate_legacy_flat_logs(retention_days=30)

        self.assertEqual(migrated, 2)
        self.assertFalse(os.path.exists(legacy_log))
        self.assertFalse(os.path.exists(old_backup))

        from src.logging.logger import current_month_dir
        current_log = os.path.join(current_month_dir(self.cleanup_mgr.logs_dir), "app.log")
        with open(current_log, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("legacy entry", content)

if __name__ == "__main__":
    unittest.main()
