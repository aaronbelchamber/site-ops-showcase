"""Git-backed asset snapshots.

The tar strategy in `assets.py` archives the whole WordPress install on the
server and streams it down to the machine running site-manager - hundreds of
megabytes per backup, before *every* update. Once a site's code lives in git
(see `src/git/manager.py`), that download is redundant: a commit already
captures the exact file state, pushing it stores an offsite copy incrementally,
and rolling back is a local operation on the server.

**This does not replace the tar strategy, and must not.** The site .gitignore
deliberately excludes `wp-content/uploads/`, `wp-config.php` and backup-plugin
output, so a git snapshot is a *code* backup, not a full one. It is therefore
used only for media-less backups - which is what the automatic pre-update
backups already are (`include_media: false`). A full backup still tars.

Restore relies on a property worth stating plainly: `git reset --hard` reverts
tracked files, and `git clean -fd` removes files added since the snapshot but
**skips ignored paths** (that needs `-x`, which is deliberately not used). So a
rollback restores plugin and core code without touching a single uploaded
media file or the site's wp-config.php.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from src.execution.base import BaseExecutor
from src.execution.shell import quote_path, is_windows_local


class GitSnapshotError(RuntimeError):
    """Raised when a git snapshot or rollback cannot be completed."""


class GitAssetBackup:
    """Capture and restore a site's code state through its git repository."""

    def __init__(self, executor: BaseExecutor, wp_path: str, remote_url: str | None = None):
        self.executor = executor
        self.wp_path = wp_path
        self.remote_url = remote_url

    @staticmethod
    def is_available(site_config: Dict[str, Any], include_media: bool) -> bool:
        """Whether a git snapshot can stand in for the tar archive.

        Requires git enabled with a remote (so the snapshot is stored offsite,
        not only on the server it is meant to protect) and a media-less backup,
        since git excludes uploads.
        """
        if include_media:
            return False
        return bool(site_config.get("git_enabled") and site_config.get("git_remote_url"))

    def _git(self, command: str, timeout: int = 600):
        if not self.wp_path:
            raise GitSnapshotError("wp_path is not defined for this site")
        quoted = quote_path(self.wp_path, "wp_path", is_windows_local(self.executor))
        prefix = "cd /d " if is_windows_local(self.executor) else "cd "
        return self.executor.execute(f"{prefix}{quoted} && {command}", timeout=timeout)

    def snapshot(self, description: str) -> Dict[str, Any]:
        """Commit the current file state and push it. Returns manifest components."""
        res = self._git("git rev-parse --is-inside-work-tree")
        if not res or not res.success:
            raise GitSnapshotError(f"{self.wp_path} is not a git repository")

        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        message = f"{description or 'Backup snapshot'} ({stamp})"
        self._git("git add -A")

        # An unchanged site is not an error - the existing HEAD already
        # describes this state, so it is a perfectly valid restore point.
        commit = self._git(f'git commit -m "{message}"')
        created = bool(commit and commit.success)

        head = self._git("git rev-parse HEAD")
        if not head or not head.success or not head.stdout.strip():
            raise GitSnapshotError("could not resolve HEAD after snapshot")
        sha = head.stdout.strip()

        pushed = False
        if self.remote_url:
            push = self._git("git push origin HEAD", timeout=1800)
            pushed = bool(push and push.success)

        return {
            "strategy": "git",
            "commit": sha,
            "committed": created,
            "pushed": pushed,
            "remote": self.remote_url,
        }

    def restore(self, commit: str) -> bool:
        """Roll the working tree back to `commit`.

        `git clean -fd` intentionally omits `-x`, so ignored paths - uploads,
        wp-config.php, backup-plugin output - are left exactly as they are.
        """
        if not commit or not all(c in "0123456789abcdef" for c in commit.lower()):
            raise GitSnapshotError(f"invalid commit id: {commit!r}")

        exists = self._git(f"git cat-file -e {commit}^{{commit}}")
        if not exists or not exists.success:
            raise GitSnapshotError(f"commit {commit} not found in {self.wp_path}")

        reset = self._git(f"git reset --hard {commit}")
        if not reset or not reset.success:
            raise GitSnapshotError(f"git reset failed: {getattr(reset, 'stderr', 'unknown')}")

        self._git("git clean -fd")
        return True
