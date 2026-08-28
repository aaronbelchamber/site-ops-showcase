import os
import json
import logging
from typing import Dict, Any, Optional
from src.execution.base import BaseExecutor
from src.execution.shell import is_windows_local, quote_path, quote_posix

logger = logging.getLogger(__name__)

DEFAULT_GITIGNORE = """# WordPress Standard .gitignore
wp-config.php
wp-content/uploads/
wp-content/blogs.dir/
wp-content/upgrade/
wp-content/backup-db/
wp-content/backups/
wp-content/cache/

# Backup-plugin output. These archives are hundreds of MB to over a GB, exceed
# GitHub's 100MB per-file hard limit, and typically embed a full database dump
# - so they are both unpushable and a credential risk. Found tracked on three
# sites on 2026-08-27.
wp-content/ai1wm-backups/
wp-content/updraft/
wp-content/backups-dup-*/
wp-content/backupwordpress-*/
*.wpress
*.sql
*.sql.gz

*.log
.htaccess
.env
node_modules/
.DS_Store
Thumbs.db
"""

class GitManager:
    """
    Manages Git version control operations for a WordPress site installation.
    Supports repository initialization, gitignore hygiene, version-formatted commits, and pushing.
    """

    def __init__(self, site_config: Dict[str, Any], executor: BaseExecutor):
        self.site_config = site_config
        self.executor = executor
        self.site_name = site_config.get("site_name") or site_config.get("display_name", "unknown")
        self.wp_path = site_config.get("wp_path", "")
        self.repo_name = f"wp-{self.site_name}"
        self.git_remote_url = site_config.get("git_remote_url")

    def _is_windows_local(self) -> bool:
        """Check if executing locally on a Windows host."""
        return is_windows_local(self.executor)

    def _get_cd_prefix(self) -> str:
        """
        Get the shell command prefix to change directory to the site's wp_path.

        wp_path is operator-supplied; double quotes alone would still allow
        $(...) / backtick substitution to execute, so it must be shell-quoted
        for whichever shell will actually run the command.
        """
        if self._is_windows_local():
            # Use /d to change drive on Windows cmd
            normalized_path = os.path.normpath(self.wp_path)
            return f'cd /d {quote_path(normalized_path, "wp_path", True)} && '
        return f'cd {quote_path(self.wp_path, "wp_path", False)} && '

    def _run_git(self, git_command: str, timeout: int = 60):
        """Execute a git command within the site wp_path directory."""
        if not self.wp_path:
            return None
        cmd = f'{self._get_cd_prefix()}{git_command}'
        return self.executor.execute(cmd, timeout=timeout)

    def is_initialized(self) -> bool:
        """Check if a .git repository directory exists in the site wp_path."""
        if not self.wp_path:
            return False
        res = self._run_git("git rev-parse --is-inside-work-tree")
        return bool(res and res.success and res.stdout.strip() == "true")

    def ensure_gitignore(self) -> bool:
        """Ensure standard .gitignore file exists in wp_path."""
        if not self.wp_path:
            return False
        # Check if .gitignore already exists
        check_res = self._run_git("test -f .gitignore || test -f .gitignore.txt")
        # On windows/linux test may behave differently, so check via git or echo
        if check_res and check_res.success:
            return True

        # Write default .gitignore safely using echo/cat
        lines = [line for line in DEFAULT_GITIGNORE.strip().split("\n") if line]
        content = "\\n".join(lines)
        create_res = self._run_git(f'printf "{content}\\n" > .gitignore')
        if not create_res or not create_res.success:
            # Fallback for Windows cmd/powershell environments
            self._run_git(f'echo "{content}" > .gitignore')
        return True

    def init_repo(self, force: bool = False) -> Dict[str, Any]:
        """
        Initialize Git repo, ensure .gitignore, create initial commit,
        and optionally configure GitHub remote repo.
        """
        if not self.wp_path:
            return {"success": False, "error": "wp_path is not defined for this site"}

        if self.is_initialized() and not force:
            status = self.get_repo_status()
            return {
                "success": True,
                "message": "Repository is already initialized",
                "status": status
            }

        # 1. git init
        init_res = self._run_git("git init")
        if not init_res or not init_res.success:
            err = init_res.stderr if init_res else "Failed to execute git init"
            return {"success": False, "error": err}

        # 2. ensure .gitignore
        self.ensure_gitignore()

        # 3. stage and initial commit
        self._run_git("git add .")
        commit_res = self._run_git('git commit -m "Initial commit of WordPress site"')

        # 4. create/configure remote
        remote_res = self._setup_github_remote()

        status = self.get_repo_status()
        return {
            "success": True,
            "message": "Git repository initialized successfully",
            "remote_setup": remote_res,
            "status": status
        }

    def _setup_github_remote(self) -> Dict[str, Any]:
        """Setup GitHub remote using gh CLI or git remote add."""
        if self.git_remote_url:
            self._run_git(f'git remote add origin "{self.git_remote_url}" || git remote set-url origin "{self.git_remote_url}"')
            return {"success": True, "remote_url": self.git_remote_url}

        # Attempt creating private repo via gh cli
        gh_cmd = f'gh repo create "{self.repo_name}" --private --source=. --remote=origin'
        gh_res = self._run_git(gh_cmd)
        if gh_res and gh_res.success:
            return {"success": True, "repo_name": self.repo_name, "created_via_gh": True}

        # If repo might already exist on GitHub, check or set remote
        remote_check = self._run_git("git remote get-url origin")
        if remote_check and remote_check.success and remote_check.stdout.strip():
            return {"success": True, "remote_url": remote_check.stdout.strip()}

        return {
            "success": False,
            "warning": f"Could not automatically create GitHub remote for {self.repo_name}. gh CLI output: {gh_res.stderr if gh_res else 'unknown'}"
        }

    def get_repo_status(self) -> Dict[str, Any]:
        """Retrieve current Git status, branch, last commit, and remote information."""
        if not self.is_initialized():
            return {
                "initialized": False,
                "branch": None,
                "remote_url": None,
                "last_commit": None,
                "has_uncommitted_changes": False
            }

        # Current branch
        branch_res = self._run_git("git rev-parse --abbrev-ref HEAD")
        branch = branch_res.stdout.strip() if branch_res and branch_res.success else "main"

        # Remote URL
        remote_res = self._run_git("git remote get-url origin")
        remote_url = remote_res.stdout.strip() if remote_res and remote_res.success else None

        # Last commit
        log_res = self._run_git('git log -1 --format="%H|%s|%an|%cI"')
        last_commit = None
        if log_res and log_res.success and log_res.stdout.strip():
            parts = log_res.stdout.strip().split("|")
            if len(parts) >= 4:
                last_commit = {
                    "hash": parts[0],
                    "short_hash": parts[0][:7],
                    "message": parts[1],
                    "author": parts[2],
                    "date": parts[3]
                }

        # Status / uncommitted changes
        status_res = self._run_git("git status --porcelain")
        has_uncommitted = bool(status_res and status_res.success and status_res.stdout.strip())

        return {
            "initialized": True,
            "branch": branch,
            "remote_url": remote_url,
            "last_commit": last_commit,
            "has_uncommitted_changes": has_uncommitted
        }

    def extract_versions_from_update(
        self,
        update_result: Dict[str, Any],
        versions_before: Optional[Dict[str, Any]] = None,
        versions_after: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Parse update results and version snapshots to generate formatted commit message.
        """
        update_type = update_result.get("type", "update")
        changes = []

        before_core = (versions_before or {}).get("core_version")
        after_core = (versions_after or {}).get("core_version")
        if before_core and after_core and before_core != after_core:
            changes.append(f"- Core: WordPress {before_core} → {after_core}")

        # Plugin diffs
        before_plugins = (versions_before or {}).get("plugins", {})
        after_plugins = (versions_after or {}).get("plugins", {})
        for name, after_ver in after_plugins.items():
            before_ver = before_plugins.get(name)
            if before_ver and before_ver != after_ver:
                changes.append(f"- Plugin: {name} {before_ver} → {after_ver}")
            elif not before_ver and after_ver:
                changes.append(f"- Plugin: {name} installed ({after_ver})")

        # Theme diffs
        before_themes = (versions_before or {}).get("themes", {})
        after_themes = (versions_after or {}).get("themes", {})
        for name, after_ver in after_themes.items():
            before_ver = before_themes.get(name)
            if before_ver and before_ver != after_ver:
                changes.append(f"- Theme: {name} {before_ver} → {after_ver}")

        # Fallback inspection of update_result if version maps weren't supplied
        if not changes:
            steps = update_result.get("steps", [])
            for step in steps:
                step_type = step.get("type", "")
                target = step.get("target", "")
                if step.get("status") == "completed":
                    changes.append(f"- {step_type.capitalize()}: {target} updated")

        if not changes:
            if update_type == "core":
                changes.append("- WordPress core updated")
            elif update_type == "plugin":
                target = update_result.get("target", "plugins")
                changes.append(f"- Plugin {target} updated")
            elif update_type == "theme":
                target = update_result.get("target", "themes")
                changes.append(f"- Theme {target} updated")
            else:
                changes.append("- Themes and plugins updated")

        title = "Updated themes and plugins" if update_type in ("all", "plugin", "theme") else "Updated WordPress core"
        body = "\n".join(changes)
        return f"{title}\n\n{body}"

    def create_update_commit(
        self,
        update_result: Dict[str, Any],
        versions_before: Optional[Dict[str, Any]] = None,
        versions_after: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Stage all changes and commit with version change details.
        """
        if not self.is_initialized():
            return {"success": False, "error": "Git repository is not initialized"}

        self.ensure_gitignore()
        self._run_git("git add .")

        # Check if there are staged changes
        diff_res = self._run_git("git diff --staged --name-only")
        if not diff_res or not diff_res.stdout.strip():
            return {"success": True, "message": "No code changes detected to commit"}

        commit_msg = self.extract_versions_from_update(update_result, versions_before, versions_after)
        # The message is assembled from plugin/theme names reported by the
        # managed WordPress site, so it is untrusted input. Escaping only `"`
        # left $(...) and backticks live; quote the whole argument instead.
        commit_res = self._run_git(f'git commit -m {quote_posix(commit_msg)}')

        if not commit_res or not commit_res.success:
            return {
                "success": False,
                "error": commit_res.stderr if commit_res else "Failed to commit changes"
            }

        status = self.get_repo_status()
        return {
            "success": True,
            "commit": status.get("last_commit"),
            "message": commit_msg
        }

    def push_to_github(self) -> Dict[str, Any]:
        """
        Push current branch commits to configured origin remote.
        Non-blocking: returns success=False on failure rather than raising.
        """
        if not self.is_initialized():
            return {"success": False, "error": "Git repository is not initialized"}

        push_res = self._run_git("git push origin HEAD")
        if push_res and push_res.success:
            return {"success": True, "output": push_res.stdout}

        err = push_res.stderr if push_res else "Unknown error running git push"
        logger.warning(f"Git push failed for site {self.site_name}: {err}")
        return {"success": False, "error": err}
