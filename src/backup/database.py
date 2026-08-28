import os
import shlex
import time
from typing import Dict, Any, List
from src.execution.base import BaseExecutor

from src.execution.shell import assert_windows_shell_safe


def _assert_windows_shell_safe(value: str, field_name: str) -> None:
    """Reject values cmd.exe cannot safely quote. See src/execution/shell.py."""
    assert_windows_shell_safe(value, f"database {field_name}", "Database")


class DatabaseBackup:
    #: A gzip stream containing nothing is exactly 20 bytes. Anything at or
    #: below this threshold is an empty or truncated dump, never a real one.
    MIN_PLAUSIBLE_DUMP_BYTES = 256

    def __init__(self, executor: BaseExecutor, db_config: Dict[str, Any], local_backup_path: str,
                 wp_path: str = ""):
        self.executor = executor
        self.db_config = db_config
        self.local_backup_path = local_backup_path
        #: Used to source DB_PASSWORD from wp-config.php when the credential
        #: store has none. See _password_expression().
        self.wp_path = wp_path

    def _password_expression(self, password: str) -> str:
        """Shell expression yielding the database password.

        A configured password is quoted and used directly. When none is stored
        - which was true of every site here - fall back to asking wp-cli for
        the value already present in wp-config.php.

        The fallback is a command substitution evaluated *on the server*, so
        the password is never transmitted to this machine, never written to the
        credential store, and never appears in a manifest or log. WordPress
        already has to keep that secret on disk to function; copying it into a
        second store would widen the exposure for no gain.
        """
        if password:
            return shlex.quote(password)
        if not self.wp_path:
            return "''"
        path = shlex.quote(self.wp_path)
        # `wp` first for a normal install, then the phar this host actually has.
        return (
            f'"$(wp config get DB_PASSWORD --path={path} 2>/dev/null '
            f'|| php ~/wp-cli.phar config get DB_PASSWORD --path={path})"'
        )

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
            _assert_windows_shell_safe(password, "password")
            _assert_windows_shell_safe(host, "host")
            _assert_windows_shell_safe(user, "user")
            _assert_windows_shell_safe(db_name, "name")
            cmd = (
                f'set "MYSQL_PWD={password}"&& '
                f'mysqldump -h "{host}" -u "{user}" "{db_name}"'
            )
        else:
            # `mysqldump | gzip` reports *gzip's* exit status, which is 0 even
            # when mysqldump fails - so a failed dump produced a 20-byte empty
            # gzip and was recorded as a completed backup. Every database
            # backup taken before 2026-08-27 was empty for this reason.
            # pipefail makes the pipeline fail when mysqldump does.
            inner = (
                f"MYSQL_PWD={self._password_expression(password)} "
                f"mysqldump -h {shlex.quote(host)} -u {shlex.quote(user)} {shlex.quote(db_name)} | gzip"
            )
            cmd = f"bash -o pipefail -c {shlex.quote(inner)}"

        res = self.executor.execute_stream(cmd, full_local_path)
        if not res.success:
            # Clean up if failed file was created
            if os.path.exists(full_local_path):
                os.remove(full_local_path)
            raise RuntimeError(f"Database dump failed: {res.stderr}")

        # Second line of defence, independent of exit status: a dump this
        # small cannot contain a schema. Catches any other silent-empty mode
        # (an empty gzip stream is 20 bytes; a trivial header only a little
        # more), so a broken backup fails loudly instead of looking complete.
        size = os.path.getsize(full_local_path)
        if size < self.MIN_PLAUSIBLE_DUMP_BYTES:
            os.remove(full_local_path)
            raise RuntimeError(
                f"Database dump for {db_name!r} was {size} bytes - too small to "
                f"contain any data, so it is being treated as a failure rather "
                f"than a completed backup. mysqldump stderr: {res.stderr or '(none)'}"
            )

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
            _assert_windows_shell_safe(password, "password")
            _assert_windows_shell_safe(host, "host")
            _assert_windows_shell_safe(user, "user")
            _assert_windows_shell_safe(db_name, "name")
            cmd = (
                f'set "MYSQL_PWD={password}"&& '
                f'mysql -h "{host}" -u "{user}" "{db_name}"'
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
