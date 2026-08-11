import os
import logging
from logging.handlers import RotatingFileHandler

# Calculate log path relative to project root
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE_PATH = os.path.join(LOGS_DIR, "app.log")

class LoggerFactory:
    @staticmethod
    def setup_logger() -> logging.Logger:
        """
        Initialize and configure the centralized rotating application logger.
        """
        os.makedirs(LOGS_DIR, exist_ok=True)
        
        logger_instance = logging.getLogger("site_manager")
        
        # Avoid adding handlers multiple times if setup_logger is called repeatedly
        if not logger_instance.handlers:
            # Load log level from environment
            log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
            log_level = getattr(logging, log_level_str, logging.INFO)
            logger_instance.setLevel(log_level)
            
            # Max file size 5MB, keep 5 backups
            file_handler = RotatingFileHandler(
                LOG_FILE_PATH,
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8"
            )
            
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ"
            )
            file_handler.setFormatter(formatter)
            logger_instance.addHandler(file_handler)
            
            # Add a console stream handler too
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger_instance.addHandler(console_handler)
            
        return logger_instance

# Shared logger instance
logger = LoggerFactory.setup_logger()
