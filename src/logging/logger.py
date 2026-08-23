import os
import time
import logging

# Calculate log path relative to project root
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")


def current_month_dir(logs_dir: str = LOGS_DIR) -> str:
    """Return (and create) the logs/YYYY-MM directory for the current UTC month."""
    month_dir = os.path.join(logs_dir, time.strftime("%Y-%m", time.gmtime()))
    os.makedirs(month_dir, exist_ok=True)
    return month_dir


class MonthlyFileHandler(logging.Handler):
    """
    Routes log records to logs/<YYYY-MM>/app.log, rolling over to a new
    monthly file automatically as the UTC month changes.
    """

    def __init__(self, logs_dir: str = LOGS_DIR, encoding: str = "utf-8"):
        super().__init__()
        self.logs_dir = logs_dir
        self.encoding = encoding
        self._current_month = None
        self._stream = None
        self._open_current_month()

    def _open_current_month(self):
        month_key = time.strftime("%Y-%m", time.gmtime())
        if month_key == self._current_month and self._stream:
            return
        if self._stream:
            self._stream.close()
        month_dir = current_month_dir(self.logs_dir)
        self._current_month = month_key
        self.baseFilename = os.path.join(month_dir, "app.log")
        self._stream = open(self.baseFilename, "a", encoding=self.encoding)

    def emit(self, record):
        try:
            self._open_current_month()
            msg = self.format(record)
            self._stream.write(msg + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self):
        if self._stream:
            self._stream.close()
        super().close()


class LoggerFactory:
    @staticmethod
    def setup_logger() -> logging.Logger:
        """
        Initialize and configure the centralized application logger.
        Writes to logs/<YYYY-MM>/app.log, self-organizing by month.
        """
        os.makedirs(LOGS_DIR, exist_ok=True)

        logger_instance = logging.getLogger("site_manager")

        # Avoid adding handlers multiple times if setup_logger is called repeatedly
        if not logger_instance.handlers:
            # Load log level from environment
            log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
            log_level = getattr(logging, log_level_str, logging.INFO)
            logger_instance.setLevel(log_level)

            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ"
            )

            file_handler = MonthlyFileHandler(LOGS_DIR)
            file_handler.setFormatter(formatter)
            logger_instance.addHandler(file_handler)

            # Add a console stream handler too
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger_instance.addHandler(console_handler)

        return logger_instance


# Shared logger instance
logger = LoggerFactory.setup_logger()
