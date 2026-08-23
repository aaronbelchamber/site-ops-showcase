import os
import sys
import getpass
import secrets
import string
import shutil
import abc
import dotenv
from typing import Dict, Any

from src.config.loader import (
    CONFIG_DIR,
    SITES_YAML_PATH,
    CREDENTIALS_ENC_PATH,
    ENV_PATH,
    PROJECT_ROOT,
    validate_site_name,
    load_sites_config,
    save_sites_config,
    load_credentials,
    save_credentials,
    load_raw_credentials,
)
from src.config.crypto import CredentialEncryptor
from src.execution import get_executor
from src.wp.cli import WPCLI
from src.health.manager import HealthCheckManager

class BaseCommand(abc.ABC):
    """Abstract base class representing a CLI Command."""
    
    @abc.abstractmethod
    def execute(self, args) -> int:
        """Execute the command with parsed arguments.
        
        Args:
            args: Namespace object from argparse.
            
        Returns:
            Exit code (0 for success, non-zero for failure).
        """
        pass


class InitCommand(BaseCommand):
    """Run initial setup, create directories, and generate templates."""
    
    def execute(self, args) -> int:
        print("Initializing WordPress Site Manager...")
        
        # Create directory structure
        dirs = [
            CONFIG_DIR,
            os.path.join(PROJECT_ROOT, "backups"),
            os.path.join(PROJECT_ROOT, "logs"),
            os.path.join(PROJECT_ROOT, "src"),
            os.path.join(PROJECT_ROOT, "src", "config"),
            os.path.join(PROJECT_ROOT, "src", "execution"),
            os.path.join(PROJECT_ROOT, "src", "wp"),
            os.path.join(PROJECT_ROOT, "src", "backup"),
            os.path.join(PROJECT_ROOT, "src", "health"),
            os.path.join(PROJECT_ROOT, "src", "update"),
            os.path.join(PROJECT_ROOT, "src", "api"),
            os.path.join(PROJECT_ROOT, "src", "logging"),
        ]
        
        for d in dirs:
            os.makedirs(d, exist_ok=True)
            # Create __init__.py files in src directories
            if "src" in d:
                init_file = os.path.join(d, "__init__.py")
                if not os.path.exists(init_file):
                    with open(init_file, "w") as f:
                        f.write("")
                    print(f"Created {os.path.relpath(init_file, PROJECT_ROOT)}")
                    
        # Create default .env template if not exists
        if not os.path.exists(ENV_PATH):
            # Generate a secure 32-character master key
            alphabet = string.ascii_letters + string.digits
            encryption_key = "".join(secrets.choice(alphabet) for _ in range(32))
            
            with open(ENV_PATH, "w", encoding="utf-8") as f:
                f.write(f"ENCRYPTION_KEY={encryption_key}\n")
                f.write("LOG_LEVEL=INFO\n")
                f.write("BACKUP_RETENTION_DAYS=30\n")
                f.write("API_TOKEN=secret-change-me\n")
            print(f"Created {os.path.relpath(ENV_PATH, PROJECT_ROOT)} with a newly generated ENCRYPTION_KEY.")
        else:
            print(".env already exists. Skipping.")
            
        # Create empty sites.yaml if not exists
        if not os.path.exists(SITES_YAML_PATH):
            with open(SITES_YAML_PATH, "w", encoding="utf-8") as f:
                f.write("sites: {}\n")
            print(f"Created empty {os.path.relpath(SITES_YAML_PATH, PROJECT_ROOT)}.")
        else:
            print("sites.yaml already exists. Skipping.")
            
        # Create credentials.enc if not exists
        if not os.path.exists(CREDENTIALS_ENC_PATH):
            # Initialize with empty encrypted dict
            dotenv.load_dotenv(ENV_PATH)
            save_credentials({})
            print(f"Created empty {os.path.relpath(CREDENTIALS_ENC_PATH, PROJECT_ROOT)}.")
        else:
            print("credentials.enc already exists. Skipping.")
            
        # Update .gitignore
        gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
        required_ignores = {
            "backups/",
            "logs/",
            "config/.env",
            "config/credentials.enc",
            "__pycache__/",
            "*.pyc"
        }
        
        existing_ignores = set()
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as f:
                existing_ignores = {line.strip() for line in f if line.strip()}
                
        missing_ignores = required_ignores - existing_ignores
        if missing_ignores:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                if os.path.exists(gitignore_path) and os.path.getsize(gitignore_path) > 0:
                    f.write("\n")
                for ignore in sorted(missing_ignores):
                    f.write(f"{ignore}\n")
            print(f"Updated {os.path.relpath(gitignore_path, PROJECT_ROOT)}.")
            
        print("Initialization completed successfully.")
        return 0


class AddSiteCommand(BaseCommand):
    """Interactive CLI command to add a new site configuration."""
    
    def execute(self, args) -> int:
        print("--- Add New WordPress Site ---")
        
        while True:
            site_name = input("Enter site identifier slug (e.g., my-blog-site): ").strip()
            if not site_name:
                print("Site identifier is required.")
                continue
            if not validate_site_name(site_name):
                print("Invalid format. Site identifier must contain only lowercase letters, numbers, and hyphens.")
                continue
                
            try:
                existing_sites = load_sites_config()
                if site_name in existing_sites:
                    overwrite = input(f"Site '{site_name}' already exists. Overwrite? (y/N): ").strip().lower()
                    if overwrite != 'y':
                        continue
            except Exception:
                pass
            break

        display_name = input("Display Name [My WordPress Site]: ").strip() or "My WordPress Site"
        ssh_host = input("SSH Host (e.g., example.com or localhost): ").strip()
        if not ssh_host:
            ssh_host = "localhost"
            
        ssh_port_str = input("SSH Port [22]: ").strip()
        ssh_port = int(ssh_port_str) if ssh_port_str else 22
        
        ssh_user = input("SSH User: ").strip() if ssh_host != "localhost" else None
        wp_path = input("WordPress path on server [/home/username/public_html]: ").strip()
        db_host = input("Database Host [localhost]: ").strip() or "localhost"
        db_name = input("Database Name: ").strip()
        db_user = input("Database User: ").strip()
        wp_cli_path = input("WP-CLI path (press Enter to auto-detect): ").strip() or None
        health_check_url = input("Health Check URL (e.g., https://example.com): ").strip()
        include_media_str = input("Include uploads/media in backups? (y/N): ").strip().lower()
        include_media = include_media_str == 'y'

        print("\n--- Sensitive Credentials (will be encrypted) ---")
        ssh_password = None
        ssh_private_key = None
        
        if ssh_host != "localhost":
            auth_type = input("SSH Authentication Type (1: Password, 2: Key File) [2]: ").strip()
            if auth_type == "1":
                ssh_password = getpass.getpass("Enter SSH Password: ")
            else:
                key_path = input("Enter local path to SSH private key: ").strip()
                if key_path:
                    expanded_path = os.path.expanduser(key_path)
                    if os.path.exists(expanded_path):
                        try:
                            with open(expanded_path, "r", encoding="utf-8") as key_file:
                                ssh_private_key = key_file.read()
                            print("SSH Private Key loaded successfully.")
                        except Exception as e:
                            print(f"Error reading private key: {e}. Key will not be stored.")
                    else:
                        print(f"Key file not found at {expanded_path}. Key will not be stored.")
                        
        db_password = getpass.getpass("Enter Database Password: ")

        try:
            dotenv.load_dotenv(ENV_PATH)
            sites = load_sites_config()
            credentials = load_raw_credentials()
        except Exception as e:
            print(f"Error loading existing configs: {e}")
            sites = {}
            credentials = {}

        sites[site_name] = {
            "display_name": display_name,
            "ssh_host": ssh_host,
            "ssh_port": ssh_port,
            "ssh_user": ssh_user,
            "wp_path": wp_path,
            "db_host": db_host,
            "db_name": db_name,
            "db_user": db_user,
            "wp_cli_path": wp_cli_path,
            "health_check_url": health_check_url,
            "include_media": include_media,
        }
        
        credentials[site_name] = {
            "ssh_password": ssh_password,
            "ssh_private_key": ssh_private_key,
            "db_password": db_password,
        }

        try:
            save_sites_config(sites)
            save_credentials(credentials)
            print(f"\nSuccessfully added/updated site '{site_name}'.")
        except Exception as e:
            print(f"\nFailed to save configuration: {e}")
            return 1
        return 0


class ListSitesCommand(BaseCommand):
    """List all currently configured sites."""
    
    def execute(self, args) -> int:
        try:
            dotenv.load_dotenv(ENV_PATH)
            sites = load_sites_config()
        except Exception as e:
            print(f"Error loading configurations: {e}")
            return 1

        if not sites:
            print("No sites configured yet. Run 'python manage.py add-site' to add one.")
            return 0

        print(f"{'Identifier (Slug)':<20} | {'Display Name':<30} | {'Host':<25} | {'URL':<30}")
        print("-" * 115)
        for name, config in sites.items():
            print(f"{name:<20} | {config['display_name']:<30} | {config['ssh_host']:<25} | {config['health_check_url']:<30}")
        return 0


class RotateKeyCommand(BaseCommand):
    """Rotate the master encryption key and re-encrypt the credentials file."""
    
    def execute(self, args) -> int:
        print("--- Rotate Encryption Key ---")
        
        dotenv.load_dotenv(ENV_PATH)
        
        try:
            old_key = os.getenv("ENCRYPTION_KEY")
            if not old_key:
                print("No ENCRYPTION_KEY found in the environment. Run 'python manage.py init' first.")
                return 1
            credentials = load_raw_credentials()
        except Exception as e:
            print(f"Failed to load existing credentials: {e}")
            return 1

        new_key_choice = input("Generate a new secure key automatically? (Y/n): ").strip().lower()
        if new_key_choice != 'n':
            alphabet = string.ascii_letters + string.digits
            new_key = "".join(secrets.choice(alphabet) for _ in range(32))
            print(f"Generated new key: {new_key}")
        else:
            new_key = getpass.getpass("Enter new Master Encryption Key: ").strip()
            if not new_key:
                print("Operation aborted. Key cannot be empty.")
                return 1
                
        try:
            encrypted_bytes = CredentialEncryptor.encrypt_credentials(credentials, new_key)
        except Exception as e:
            print(f"Failed to encrypt credentials with the new key: {e}")
            return 1

        temp_credentials_path = CREDENTIALS_ENC_PATH + ".tmp"
        try:
            with open(temp_credentials_path, "wb") as f:
                f.write(encrypted_bytes)
        except Exception as e:
            print(f"Failed to write temporary credentials file: {e}")
            return 1

        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            key_found = False
            new_lines = []
            for line in lines:
                if line.startswith("ENCRYPTION_KEY="):
                    new_lines.append(f"ENCRYPTION_KEY={new_key}\n")
                    key_found = True
                else:
                    new_lines.append(line)
                    
            if not key_found:
                new_lines.append(f"ENCRYPTION_KEY={new_key}\n")
                
            with open(ENV_PATH, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
                
        except Exception as e:
            print(f"Failed to update .env with the new key: {e}")
            if os.path.exists(temp_credentials_path):
                os.remove(temp_credentials_path)
            return 1

        try:
            if os.path.exists(CREDENTIALS_ENC_PATH):
                shutil.copy2(CREDENTIALS_ENC_PATH, CREDENTIALS_ENC_PATH + ".bak")
            shutil.move(temp_credentials_path, CREDENTIALS_ENC_PATH)
            if os.path.exists(CREDENTIALS_ENC_PATH + ".bak"):
                os.remove(CREDENTIALS_ENC_PATH + ".bak")
            print("Successfully rotated master key and re-encrypted credentials.")
        except Exception as e:
            print(f"Failed to replace credentials file: {e}")
            print("WARNING: Key might be updated in .env but file rotation failed. Restoring .env backup is recommended.")
            return 1
        return 0


class TestConnectionCommand(BaseCommand):
    """Test SSH connectivity and WP-CLI status for one or all sites."""
    
    def execute(self, args) -> int:
        dotenv.load_dotenv(ENV_PATH)

        try:
            sites = load_sites_config()
            credentials = load_credentials()
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return 1

        if not sites:
            print("No sites configured yet. Run 'python manage.py add-site' to add one.")
            return 0

        if args.site:
            if args.site not in sites:
                print(f"Site '{args.site}' is not configured.")
                return 1
            sites_to_test = {args.site: sites[args.site]}
        else:
            sites_to_test = sites

        print(f"Testing connectivity and WP-CLI for {len(sites_to_test)} site(s)...")
        print("-" * 80)

        has_failures = False
        for name, config in sites_to_test.items():
            print(f"Site: {name} ({config.get('display_name', 'No Name')})")
            print(f"  Target: {config.get('ssh_host', 'localhost')}:{config.get('ssh_port', 22)}")
            
            executor = None
            try:
                executor = get_executor(config, credentials)
                print("  Connecting...")
                if not executor.test_connection():
                    print("  [ERROR] Connection test failed! Please check your SSH config, key, or password.")
                    print("-" * 80)
                    has_failures = True
                    continue
                print("  [SUCCESS] Connected successfully.")

                wp_path = config.get("wp_path")
                wp_cli_path = config.get("wp_cli_path")
                print(f"  Checking WP-CLI at: {wp_path}...")
                wp = WPCLI(executor, wp_path, wp_cli_path)
                
                if wp.check_installed():
                    version = wp.get_version()
                    print(f"  [SUCCESS] WP-CLI is installed. Version: {version}")
                    try:
                        wp_version = wp.get_core_version()
                        print(f"  WordPress Core Version: {wp_version}")
                    except Exception as e:
                        print(f"  [WARNING] Failed to fetch WordPress Core version: {e}")
                else:
                    print("  [WARNING] WP-CLI is not installed/detected on the target.")
                    do_install = args.auto_install
                    if not do_install:
                        try:
                            if sys.stdin.isatty():
                                resp = input("  Would you like to attempt auto-installing WP-CLI? (y/N): ").strip().lower()
                                do_install = (resp == 'y')
                            else:
                                print("  Non-interactive environment detected. Skipping auto-install prompt.")
                        except Exception:
                            pass
                    
                    if do_install:
                        print("  Attempting WP-CLI installation...")
                        if wp.install():
                            print(f"  [SUCCESS] WP-CLI installed successfully! Version: {wp.get_version()}")
                        else:
                            print("  [ERROR] WP-CLI auto-installation failed.")
                            has_failures = True
                    else:
                        print("  Skipping WP-CLI installation.")
                
            except Exception as e:
                print(f"  [ERROR] An unexpected error occurred: {e}")
                has_failures = True
            finally:
                if executor:
                    try:
                        executor.disconnect()
                    except Exception:
                        pass
            print("-" * 80)
            
        return 1 if has_failures else 0


class HealthCheckCommand(BaseCommand):
    """Run health checks for one or all sites."""
    
    def execute(self, args) -> int:
        dotenv.load_dotenv(ENV_PATH)

        try:
            sites = load_sites_config()
            credentials = load_credentials()
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return 1

        if not sites:
            print("No sites configured yet. Run 'python manage.py add-site' to add one.")
            return 0

        if args.site:
            if args.site not in sites:
                print(f"Site '{args.site}' is not configured.")
                return 1
            sites_to_test = {args.site: sites[args.site]}
        else:
            sites_to_test = sites

        print(f"Running health checks for {len(sites_to_test)} site(s)...")
        print("=" * 80)

        for name, config in sites_to_test.items():
            if "site_name" not in config:
                config["site_name"] = name
                
            print(f"Site: {name} ({config.get('display_name', 'No Name')})")
            print(f"URL: {config.get('health_check_url', 'No URL')}")
            print("Running checks, please wait...")
            
            executor = None
            try:
                executor = get_executor(config, credentials)
                wp_path = config.get("wp_path")
                wp_cli_path = config.get("wp_cli_path")
                wp = WPCLI(executor, wp_path, wp_cli_path)
                
                manager = HealthCheckManager(config, executor, wp)
                report = manager.run_all_checks()
                
                status = report.get("overall_status", "unknown").upper()
                status_indicator = f"[{status}]"
                
                print("-" * 80)
                print(f"OVERALL STATUS: {status_indicator}")
                print("-" * 80)
                
                checks = report.get("checks", {})
                http = checks.get("http", {})
                print("[HTTP Check]")
                print(f"  Status Code:   {http.get('status_code')} ({http.get('status', 'fail').upper()})")
                print(f"  Response Time: {http.get('response_time_ms')} ms")
                
                wp_core = checks.get("wp_core", {})
                print("[WordPress Core]")
                print(f"  Version:       {wp_core.get('version')}")
                print(f"  Status:        {wp_core.get('status', 'fail').upper()}")
                
                plugins = checks.get("plugins", {})
                print("[Plugins]")
                print(f"  Active Count:  {plugins.get('active_count')}")
                print(f"  Updates Avail: {plugins.get('updates_available')}")
                print(f"  Status:        {plugins.get('status', 'fail').upper()}")
                
                db = checks.get("database", {})
                print("[Database Connection]")
                print(f"  Connection:    {db.get('connection')}")
                print(f"  Status:        {db.get('status', 'fail').upper()}")
                
            except Exception as e:
                print(f"  [ERROR] Health check failed: {e}")
            finally:
                if executor:
                    try:
                        executor.disconnect()
                    except Exception:
                        pass
            print("=" * 80)
        return 0


class HealthHistoryCommand(BaseCommand):
    """Retrieve and display health check history for a site."""
    
    def execute(self, args) -> int:
        dotenv.load_dotenv(ENV_PATH)

        try:
            sites = load_sites_config()
            if args.site not in sites:
                print(f"Site '{args.site}' is not configured.")
                return 1
                
            config = sites[args.site]
            if "site_name" not in config:
                config["site_name"] = args.site
                
            manager = HealthCheckManager(config, None, None)
            history = manager.get_health_history()
            
            if not history:
                print(f"No health check history found for site '{args.site}'.")
                return 0
                
            print(f"Health Check History for '{args.site}' (Last {args.limit} entries):")
            print("-" * 100)
            print(f"{'Timestamp':<20} | {'Status':<10} | {'HTTP Code':<9} | {'Resp Time':<9} | {'WP Core':<8} | {'Plugins (Act/Up)':<16} | {'DB':<6}")
            print("-" * 100)
            
            for entry in history[:args.limit]:
                timestamp = entry.get("timestamp", "N/A")
                status = entry.get("overall_status", "unknown").upper()
                checks = entry.get("checks", {})
                
                http = checks.get("http", {})
                http_code = http.get("status_code", "N/A")
                resp_time = f"{http.get('response_time_ms', 'N/A')}ms"
                
                wp_core = checks.get("wp_core", {})
                wp_status = wp_core.get("status", "N/A").upper()
                
                plugins = checks.get("plugins", {})
                plugin_info = f"{plugins.get('active_count', 0)}/{plugins.get('updates_available', 0)}"
                
                db = checks.get("database", {})
                db_status = db.get("status", "N/A").upper()
                
                print(f"{timestamp:<20} | {status:<10} | {http_code:<9} | {resp_time:<9} | {wp_status:<8} | {plugin_info:<16} | {db_status:<6}")
            print("-" * 100)
        except Exception as e:
            print(f"Error loading health history: {e}")
            return 1
        return 0


def _kill_process_on_port(port: int):
    executor = get_executor()
    if hasattr(executor, "kill_port_process"):
        executor.kill_port_process(port)


class RunServerCommand(BaseCommand):
    """Start the Web Dashboard API server."""
    
    def execute(self, args: Any) -> int:
        import os

        dotenv.load_dotenv(ENV_PATH)

        # Under Flask's Werkzeug reloader (when debug=True), the execution runs twice:
        # first in the parent process, then in the child process.
        # We only clean up the port in the parent process (or if reloader is disabled)
        # to avoid interfering with the reloader's own child process on auto-reload.
        is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

        if not is_reloader_child:
            _kill_process_on_port(args.port)

        from src.api.app import create_app, start_cleanup_scheduler
        debug_mode = not args.no_debug
        print(f"Starting server on {args.host}:{args.port} (debug={debug_mode})...")

        start_cleanup_scheduler(debug=debug_mode)

        app = create_app()
        app.run(host=args.host, port=args.port, debug=debug_mode)

        return 0


class HealthDashboardCommand(BaseCommand):
    """Start a standalone Production Health dashboard on its own port, independent of runserver."""

    def execute(self, args: Any) -> int:
        import os

        dotenv.load_dotenv(ENV_PATH)

        # Flags this process as the locked-down, read-mostly dashboard via /api/system/mode
        # so the frontend hides Admin/Manage Sites and lands directly on Production Health.
        os.environ["APP_MODE"] = "health-dashboard"

        is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
        if not is_reloader_child:
            _kill_process_on_port(args.port)

        from src.api.app import create_app, start_cleanup_scheduler
        debug_mode = not args.no_debug
        print(f"Starting Production Health dashboard on {args.host}:{args.port} (debug={debug_mode})...")

        start_cleanup_scheduler(debug=debug_mode)

        app = create_app()
        app.run(host=args.host, port=args.port, debug=debug_mode)
        return 0


class CleanupCommand(BaseCommand):
    """Run system cleanup to prune old backups and log entries."""
    
    def execute(self, args) -> int:
        dotenv.load_dotenv(ENV_PATH)
        
        days = args.days
        log_days = days
        if days is None:
            try:
                days = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
            except Exception:
                days = 30
            try:
                log_days = int(os.getenv("LOG_RETENTION_DAYS", "30"))
            except Exception:
                log_days = 30
        else:
            log_days = days
            
        print(f"Starting system cleanup (backup retention: {days} days, log retention: {log_days} days)...")
        
        from src.logging.cleanup import CleanupManager
        cleanup_mgr = CleanupManager()
        
        if not args.logs_only:
            print(f"Cleaning up old backups (retention: {days} days)...")
            try:
                deleted_backups = cleanup_mgr.cleanup_old_backups(days)
                print(f"  [SUCCESS] Deleted {deleted_backups} old backups.")
            except Exception as e:
                print(f"  [ERROR] Backup cleanup failed: {e}")
                
        if not args.backups_only:
            print(f"Pruning old health/update JSONL log entries and app.log (retention: {log_days} days)...")
            try:
                pruned_logs = cleanup_mgr.cleanup_old_logs(log_days)
                print(f"  [SUCCESS] Pruned {pruned_logs} log file(s).")
            except Exception as e:
                print(f"  [ERROR] Log cleanup failed: {e}")
                
        print("Cleanup completed successfully.")
        return 0


class SetupGDriveCommand(BaseCommand):
    """Run interactive Google Drive Setup Wizard for automated config backups."""
    
    def execute(self, args) -> int:
        print("\n=== Google Drive Integration Setup Wizard ===")
        gdrive_path = getattr(args, "gdrive_path", None)
        
        if not gdrive_path:
            existing_path = os.getenv("GOOGLE_DRIVE_BACKUP_PATH", "")
            prompt_str = f"Enter path to your Google Drive backup directory [{existing_path}]: " if existing_path else "Enter path to your Google Drive backup directory (e.g. G:\\My Drive\\WPBackups): "
            gdrive_path = input(prompt_str).strip()
            if not gdrive_path and existing_path:
                gdrive_path = existing_path

        if not gdrive_path:
            print("[ERROR] Google Drive path cannot be empty.")
            return 1

        from src.config.system_backup import SystemBackupManager
        print(f"\n[1/3] Verifying path & write access: '{gdrive_path}'...")
        verification = SystemBackupManager.verify_gdrive_path(gdrive_path)
        
        if not verification.get("valid"):
            print(f"[ERROR] {verification.get('message')}")
            return 1
            
        print("  [SUCCESS] Path verified and writable.")

        print(f"\n[2/3] Saving GOOGLE_DRIVE_BACKUP_PATH to '{ENV_PATH}'...")
        dotenv.set_key(ENV_PATH, "GOOGLE_DRIVE_BACKUP_PATH", gdrive_path)
        os.environ["GOOGLE_DRIVE_BACKUP_PATH"] = gdrive_path
        print("  [SUCCESS] Environment configuration saved.")

        print("\n[3/3] Executing test system backup to verify end-to-end sync...")
        try:
            backup_file = SystemBackupManager.create_backup()
            print(f"  [SUCCESS] Backup created: {backup_file}")
            print(f"  [SUCCESS] System backup successfully copied to Google Drive at: {gdrive_path}")
            print("\n=== Setup Wizard Completed Successfully! ===")
            return 0
        except Exception as err:
            print(f"  [ERROR] Backup creation or copy failed: {err}")
            return 1


class GitInitCommand(BaseCommand):
    """Initialize Git repository and GitHub remote for a site or all sites."""
    
    def execute(self, args) -> int:
        from src.git.manager import GitManager
        sites = load_sites_config()
        credentials = load_credentials()
        
        target_sites = []
        if getattr(args, "all", False):
            target_sites = list(sites.keys())
        elif getattr(args, "site", None):
            if args.site not in sites:
                print(f"[ERROR] Site '{args.site}' not found in configuration.")
                return 1
            target_sites = [args.site]
        else:
            print("[ERROR] Must specify either --site <name> or --all.")
            return 1

        force = getattr(args, "force", False)
        success_count = 0

        for site_name in target_sites:
            site_config = {**sites[site_name], "site_name": site_name}
            print(f"\n--- Initializing Git for site: {site_name} ---")
            if site_config.get("status") != "Ready":
                print(f"  [SKIP] Site status is '{site_config.get('status')}', must be 'Ready'.")
                continue

            executor = get_executor(site_config, credentials)
            try:
                git_mgr = GitManager(site_config, executor)
                result = git_mgr.init_repo(force=force)
                if result.get("success"):
                    print(f"  [SUCCESS] {result.get('message')}")
                    if result.get("remote_setup", {}).get("remote_url"):
                        print(f"  [REMOTE] Remote configured: {result['remote_setup']['remote_url']}")
                    success_count += 1
                else:
                    print(f"  [ERROR] {result.get('error')}")
            finally:
                executor.disconnect()

        print(f"\nCompleted: {success_count}/{len(target_sites)} site repositories initialized.")
        return 0 if success_count == len(target_sites) else 1


class GitStatusCommand(BaseCommand):
    """Inspect Git repository status and remote details for a site."""
    
    def execute(self, args) -> int:
        from src.git.manager import GitManager
        sites = load_sites_config()
        credentials = load_credentials()

        if not getattr(args, "site", None) or args.site not in sites:
            print(f"[ERROR] Must specify a valid site via --site <name>.")
            return 1

        site_name = args.site
        site_config = {**sites[site_name], "site_name": site_name}
        executor = get_executor(site_config, credentials)
        try:
            git_mgr = GitManager(site_config, executor)
            status = git_mgr.get_repo_status()
            print(f"\n=== Git Status for {site_name} ===")
            print(f"  Initialized: {status.get('initialized')}")
            if status.get("initialized"):
                print(f"  Branch:      {status.get('branch')}")
                print(f"  Remote:      {status.get('remote_url') or 'None'}")
                print(f"  Dirty:       {status.get('has_uncommitted_changes')}")
                last_commit = status.get("last_commit")
                if last_commit:
                    print(f"  Last Commit: [{last_commit.get('short_hash')}] {last_commit.get('message')} ({last_commit.get('author')}, {last_commit.get('date')})")
            return 0
        finally:
            executor.disconnect()


class GitPushCommand(BaseCommand):
    """Manually push Git commits to origin remote for a site."""
    
    def execute(self, args) -> int:
        from src.git.manager import GitManager
        sites = load_sites_config()
        credentials = load_credentials()

        if not getattr(args, "site", None) or args.site not in sites:
            print(f"[ERROR] Must specify a valid site via --site <name>.")
            return 1

        site_name = args.site
        site_config = {**sites[site_name], "site_name": site_name}
        executor = get_executor(site_config, credentials)
        try:
            git_mgr = GitManager(site_config, executor)
            print(f"Pushing Git repository for '{site_name}' to remote...")
            result = git_mgr.push_to_github()
            if result.get("success"):
                print("  [SUCCESS] Pushed successfully to origin.")
                return 0
            else:
                print(f"  [ERROR] {result.get('error')}")
                return 1
        finally:
            executor.disconnect()


