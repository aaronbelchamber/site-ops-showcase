import os
import json
import shlex
from typing import Optional, List, Dict, Any
from src.execution.base import BaseExecutor, CommandResult
from src.execution.local import LocalExecutor

class WPCLI:
    def __init__(self, executor: BaseExecutor, wp_path: str, wp_cli_path: Optional[str] = None):
        self.executor = executor
        self.wp_path = wp_path
        self.configured_wp_cli_path = wp_cli_path
        self.detected_wp_command: Optional[str] = None
        
    def _is_windows_local(self) -> bool:
        """Check if executing locally on a Windows host."""
        return isinstance(self.executor, LocalExecutor) and os.name == "nt"

    def _get_cd_prefix(self) -> str:
        """Get the shell command prefix to change directory to the WordPress path."""
        if self._is_windows_local():
            # Use /d to change drive on Windows cmd
            normalized_path = os.path.normpath(self.wp_path)
            return f'cd /d "{normalized_path}" && '
        else:
            return f'cd "{self.wp_path}" && '

    def _get_candidates(self) -> List[str]:
        """Get the list of command candidates to try for running WP-CLI."""
        candidates = []
        
        # 1. Configured path
        if self.configured_wp_cli_path:
            path = self.configured_wp_cli_path
            if path.endswith(".phar"):
                candidates.append(f"php {path}")
            else:
                candidates.append(path)
                
        # 2. Standard global command
        candidates.append("wp")
        
        # 3. User-local candidate paths (Unix-like environments)
        if not self._is_windows_local():
            candidates.append("php ~/wp-cli.phar")
            candidates.append("~/bin/wp")
            candidates.append("~/.local/bin/wp")
            
        return candidates

    def check_installed(self) -> bool:
        """
        Check if WP-CLI is available by running a basic command.
        Probes candidate paths and saves the working one.
        """
        # If we already detected a working command, double check it
        if self.detected_wp_command:
            test_res = self.executor.execute(f"{self._get_cd_prefix()}{self.detected_wp_command} --info", timeout=10)
            if test_res.success:
                return True
            self.detected_wp_command = None

        candidates = self._get_candidates()
        for cmd in candidates:
            # Check if command is executable and prints info
            test_res = self.executor.execute(f"{self._get_cd_prefix()}{cmd} --info", timeout=10)
            if test_res.success:
                self.detected_wp_command = cmd
                return True
                
        return False

    def install(self) -> bool:
        """
        Install WP-CLI to a user-local directory (e.g. ~/wp-cli.phar) if not already installed.
        Downloads the phar file via curl or wget.
        """
        if self.check_installed():
            return True
            
        # If Windows local, installing via shell curl is tricky. We'll try, but warn.
        download_url = "https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar"
        
        if self._is_windows_local():
            # Local Windows installation attempt in current directory or user home
            local_dest = os.path.join(os.path.expanduser("~"), "wp-cli.phar")
            # We can download using PowerShell Invoke-WebRequest
            cmd = f'powershell -Command "Invoke-WebRequest -Uri {download_url} -OutFile \'{local_dest}\'"'
            res = self.executor.execute(cmd, timeout=60)
            if res.success:
                self.detected_wp_command = f"php {shlex.quote(local_dest)}"
                return self.check_installed()
            return False
        else:
            # Remote SSH or Local Linux/macOS
            # Download to ~/wp-cli.phar which is always writable
            dest_phar = "~/wp-cli.phar"
            
            # Try curl first, fallback to wget
            download_cmd = (
                f"curl -s -L -o {dest_phar} {download_url} || "
                f"wget -q -O {dest_phar} {download_url}"
            )
            res = self.executor.execute(download_cmd, timeout=60)
            if not res.success:
                return False
                
            # Make executable
            self.executor.execute(f"chmod +x {dest_phar}", timeout=10)
            
            self.detected_wp_command = f"php {dest_phar}"
            return self.check_installed()

    def run_command(self, args: List[str], parse_json: bool = False) -> CommandResult:
        """
        Execute a WP-CLI command with arguments.
        Automatically checks for and installs WP-CLI if missing.
        """
        if not self.detected_wp_command:
            if not self.check_installed():
                if not self.install():
                    return CommandResult(
                        exit_code=-1,
                        stdout="",
                        stderr="WP-CLI is not installed and auto-installation failed.",
                        success=False
                    )

        # Build arguments list
        full_args = list(args)
        if parse_json:
            # If not already specified, add format=json
            if not any(arg.startswith("--format=") for arg in full_args):
                full_args.append("--format=json")

        # Quote arguments safely using shlex.join
        args_str = shlex.join(full_args)
        
        full_cmd = f"{self._get_cd_prefix()}{self.detected_wp_command} {args_str}"
        res = self.executor.execute(full_cmd)
        if res.success and parse_json and res.stdout:
            try:
                parsed = json.loads(res.stdout)
                setattr(res, "data", parsed)
            except Exception:
                setattr(res, "data", None)
        else:
            setattr(res, "data", None)
        return res

    def get_version(self) -> str:
        """Get the WP-CLI version string."""
        res = self.run_command(["--version"])
        if res.success:
            return res.stdout.strip()
        return "Unknown"

    def get_core_version(self) -> str:
        """Get WordPress core version."""
        res = self.run_command(["core", "version"])
        if res.success:
            return res.stdout.strip()
        raise ValueError(f"Failed to get WordPress core version: {res.stderr}")

    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all installed plugins with details."""
        res = self.run_command(["plugin", "list"], parse_json=True)
        if res.success:
            try:
                return json.loads(res.stdout)
            except json.JSONDecodeError:
                raise ValueError(f"Failed to parse plugin list JSON: {res.stdout}")
        raise ValueError(f"Failed to list plugins: {res.stderr}")

    def list_themes(self) -> List[Dict[str, Any]]:
        """List all installed themes with details."""
        res = self.run_command(["theme", "list"], parse_json=True)
        if res.success:
            try:
                return json.loads(res.stdout)
            except json.JSONDecodeError:
                raise ValueError(f"Failed to parse theme list JSON: {res.stdout}")
        raise ValueError(f"Failed to list themes: {res.stderr}")

    def check_core_update(self) -> List[Dict[str, Any]]:
        """Check for core updates. Returns list of available update offers."""
        res = self.run_command(["core", "check-update"], parse_json=True)
        if res.success:
            try:
                # If there are no updates, wp core check-update prints empty list or success message.
                # Usually returns JSON array.
                return json.loads(res.stdout) if res.stdout.strip() else []
            except json.JSONDecodeError:
                return []
        # Exit code 1 is returned by WP-CLI if there is an error, but if no updates it can be 0 or 1 depending on version.
        # Let's parse JSON if output looks like JSON, else return empty.
        try:
            return json.loads(res.stdout)
        except Exception:
            return []

    def check_plugin_updates(self) -> List[Dict[str, Any]]:
        """Check for plugin updates. Returns list of plugins with updates available."""
        res = self.run_command(["plugin", "list", "--update=available"], parse_json=True)
        if res.success:
            try:
                return json.loads(res.stdout)
            except json.JSONDecodeError:
                return []
        return []

    def check_theme_updates(self) -> List[Dict[str, Any]]:
        """Check for theme updates. Returns list of themes with updates available."""
        res = self.run_command(["theme", "list", "--update=available"], parse_json=True)
        if res.success:
            try:
                return json.loads(res.stdout)
            except json.JSONDecodeError:
                return []
        return []

    def scan_server_sites(self, search_root: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Scan server directories to discover WordPress installations containing wp-config.php.
        """
        if self._is_windows_local():
            cmd = 'dir /b /s wp-config.php'
            res = self.executor.execute(cmd, timeout=30)
            if not res.success:
                return []
            found_paths = []
            for line in res.stdout.splitlines():
                line = line.strip()
                if line.endswith("wp-config.php"):
                    found_paths.append(os.path.dirname(line))
        else:
            base_dir = search_root if search_root else "$HOME"
            cmd = f"find {base_dir} -maxdepth 3 -name wp-config.php 2>/dev/null"
            res = self.executor.execute(cmd, timeout=30)
            if not res.success:
                return []
            found_paths = [os.path.dirname(p.strip()) for p in res.stdout.splitlines() if p.strip()]

        discovered = []
        for path in found_paths:
            # Check site name/url/db_name/db_user via wp-cli or config inspect if possible
            site_info = {"wp_path": path, "name": os.path.basename(path), "url": "", "db_name": "", "db_user": ""}
            try:
                sub_cli = WPCLI(self.executor, wp_path=path, wp_cli_path=self.configured_wp_cli_path)
                home_res = sub_cli.run_command(["option", "get", "home"])
                if home_res.success and home_res.stdout.strip():
                    url_val = home_res.stdout.strip()
                    if url_val.endswith("/cms"):
                        url_val = url_val[:-4]
                    site_info["url"] = url_val
                else:
                    url_res = sub_cli.run_command(["option", "get", "siteurl"])
                    if url_res.success and url_res.stdout.strip():
                        url_val = url_res.stdout.strip()
                        if url_val.endswith("/cms"):
                            url_val = url_val[:-4]
                        site_info["url"] = url_val
                name_res = sub_cli.run_command(["option", "get", "blogname"])
                if name_res.success and name_res.stdout.strip():
                    site_info["name"] = name_res.stdout.strip()
                
                # Fetch DB details via config get
                db_name_res = sub_cli.run_command(["config", "get", "DB_NAME"])
                if db_name_res.success:
                    site_info["db_name"] = db_name_res.stdout.strip()
                db_user_res = sub_cli.run_command(["config", "get", "DB_USER"])
                if db_user_res.success:
                    site_info["db_user"] = db_user_res.stdout.strip()
            except Exception:
                pass
            discovered.append(site_info)


        return discovered

    def list_users(self) -> List[Dict[str, Any]]:
        """List all users on the WordPress site."""
        res = self.run_command(["user", "list", "--fields=ID,user_login,display_name,user_email,roles,user_registered"], parse_json=True)
        if res.success:
            try:
                return json.loads(res.stdout)
            except json.JSONDecodeError:
                raise ValueError(f"Failed to parse user list JSON: {res.stdout}")
        raise ValueError(f"Failed to list users: {res.stderr}")

    def update_user_role(self, user_id: int, role: str) -> bool:
        """Update a user's role."""
        res = self.run_command(["user", "set-role", str(user_id), role])
        return res.success

    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate a user account by setting role to subscriber and randomizing password."""
        role_res = self.update_user_role(user_id, "subscriber")
        import uuid
        random_pass = str(uuid.uuid4())
        pass_res = self.run_command(["user", "update", str(user_id), f"--user_pass={random_pass}"])
        return role_res and pass_res.success

    def delete_user(self, user_id: int, reassign_id: int) -> bool:
        """Delete a user account and reassign posts to reassign_id."""
        res = self.run_command(["user", "delete", str(user_id), f"--reassign={reassign_id}", "--yes"])
        return res.success

    def _extract_json(self, text: str) -> Optional[Any]:
        """Extract JSON structure from stdout even if preceded by PHP warnings or preamble."""
        if not text:
            return None
        start_bracket = text.find("[")
        start_brace = text.find("{")
        
        start_idx = -1
        if start_bracket != -1 and start_brace != -1:
            start_idx = min(start_bracket, start_brace)
        elif start_bracket != -1:
            start_idx = start_bracket
        elif start_brace != -1:
            start_idx = start_brace
            
        if start_idx == -1:
            return None
            
        end_bracket = text.rfind("]")
        end_brace = text.rfind("}")
        end_idx = max(end_bracket, end_brace)
        
        if end_idx <= start_idx:
            return None
            
        json_str = text[start_idx:end_idx + 1]
        try:
            return json.loads(json_str)
        except Exception:
            return None

    def check_vulnerabilities(self) -> Dict[str, Any]:
        """
        Check vulnerabilities via WP-CLI package or fallback audit.
        """
        # Try candidate vulnerability scan commands
        scan_cmds = [
            ["vulnerability", "check"],
            ["vulnerability", "check-plugins"],
            ["vulnerability-scanner", "scan"]
        ]

        for cmd in scan_cmds:
            res = self.run_command(cmd, parse_json=True)
            json_data = self._extract_json(res.stdout)
            if json_data is not None:
                return {
                    "status": "success",
                    "package_installed": True,
                    "data": json_data
                }

        # Check if package is listed in wp package list even if scan output had no vulnerabilities/JSON
        pkg_res = self.run_command(["package", "list"], parse_json=True)
        pkg_json = self._extract_json(pkg_res.stdout)
        is_pkg_installed = False
        if isinstance(pkg_json, list):
            for pkg in pkg_json:
                name = pkg.get("name", "")
                if "vulnerability" in name:
                    is_pkg_installed = True
                    break

        if is_pkg_installed:
            return {
                "status": "success",
                "package_installed": True,
                "data": []
            }

        # Package not installed or command failed; gather core/plugin/theme version info for audit
        plugins = self.list_plugins() if self.check_installed() else []
        themes = self.list_themes() if self.check_installed() else []
        core_ver = self.get_core_version() if self.check_installed() else "Unknown"

        return {
            "status": "fallback",
            "package_installed": False,
            "message": "WP-CLI vulnerability extension not installed. Click 'Install Extension' or run 'wp package install 10up/wpcli-vulnerability-scanner:dev-master'",
            "audit_data": {
                "core_version": core_ver,
                "plugins": plugins,
                "themes": themes
            }
        }


    def install_vulnerability_package(self) -> CommandResult:
        """
        Install the WP-CLI vulnerability scanner package (10up/wpcli-vulnerability-scanner).
        Tries package identifiers in sequence and falls back to git repo URL.
        """
        candidates = [
            ["package", "install", "10up/wpcli-vulnerability-scanner:dev-master"],
            ["package", "install", "10up/wpcli-vulnerability-scanner"],
            ["package", "install", "https://github.com/10up/wpcli-vulnerability-scanner.git"]
        ]
        
        last_res = None
        for cmd in candidates:
            res = self.run_command(cmd)
            if res.success:
                return res
            last_res = res

        return last_res




