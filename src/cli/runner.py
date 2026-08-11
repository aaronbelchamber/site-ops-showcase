import argparse
import sys
from typing import Dict, Type

from src.cli.commands import (
    BaseCommand,
    InitCommand,
    AddSiteCommand,
    ListSitesCommand,
    RotateKeyCommand,
    TestConnectionCommand,
    HealthCheckCommand,
    HealthHistoryCommand,
    RunServerCommand,
    CleanupCommand,
    SetupGDriveCommand,
)

class SiteManagerCLI:
    """Argparse command router mapping subcommands to Command instances."""
    
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            description="WordPress Site Manager - CLI Management Utility"
        )
        self.subparsers = self.parser.add_subparsers(dest="command", help="Command to run")
        self.commands: Dict[str, BaseCommand] = {}
        
        self._register_commands()

    def _register(self, name: str, cmd_class: Type[BaseCommand], parser_setup_fn=None) -> argparse.ArgumentParser:
        """Register a command mapping and create its subparser."""
        self.commands[name] = cmd_class()
        # Retrieve the first line of the docstring for the help text
        doc = cmd_class.__doc__
        help_text = doc.split("\n")[0] if doc else ""
        subparser = self.subparsers.add_parser(name, help=help_text)
        if parser_setup_fn:
            parser_setup_fn(subparser)
        return subparser

    def _register_commands(self):
        # 1. init
        self._register("init", InitCommand)
        
        # 2. add-site
        self._register("add-site", AddSiteCommand)
        
        # 3. list-sites
        self._register("list-sites", ListSitesCommand)
        
        # 4. rotate-key
        self._register("rotate-key", RotateKeyCommand)
        
        # 5. test-connection
        def setup_test_conn(p):
            p.add_argument("--site", help="Specific site slug to test")
            p.add_argument("--auto-install", action="store_true", help="Auto-install WP-CLI if missing")
        self._register("test-connection", TestConnectionCommand, setup_test_conn)
        
        # 6. health-check
        def setup_health_chk(p):
            p.add_argument("--site", help="Specific site slug to check")
        self._register("health-check", HealthCheckCommand, setup_health_chk)
        
        # 7. health-history
        def setup_health_hist(p):
            p.add_argument("--site", required=True, help="Specific site slug to show history for")
            p.add_argument("--limit", type=int, default=10, help="Number of history entries to show")
        self._register("health-history", HealthHistoryCommand, setup_health_hist)
        
        # 8. runserver
        def setup_runserver(p):
            p.add_argument("--host", default="127.0.0.1", help="Host address to bind to")
            p.add_argument("--port", type=int, default=5000, help="Port to listen on")
            p.add_argument("--no-debug", action="store_true", help="Disable debug mode")
        self._register("runserver", RunServerCommand, setup_runserver)
        
        # 9. cleanup
        def setup_cleanup(p):
            p.add_argument("--days", type=int, help="Retention period in days (default: read from .env)")
            p.add_argument("--backups-only", action="store_true", help="Only prune old backup files")
            p.add_argument("--logs-only", action="store_true", help="Only prune old health/update log entries")
        self._register("cleanup", CleanupCommand, setup_cleanup)

        # 10. setup-gdrive
        def setup_gdrive_cmd(p):
            p.add_argument("--path", dest="gdrive_path", help="Target Google Drive backup directory path")
        self._register("setup-gdrive", SetupGDriveCommand, setup_gdrive_cmd)

    def run(self, argv=None) -> int:
        args = self.parser.parse_args(argv)
        if not args.command:
            self.parser.print_help()
            return 0
            
        cmd = self.commands.get(args.command)
        if not cmd:
            print(f"Unknown command: {args.command}")
            self.parser.print_help()
            return 1
            
        try:
            return cmd.execute(args)
        except Exception as e:
            print(f"Error executing command '{args.command}': {e}", file=sys.stderr)
            return 1

class CLIApp:
    @staticmethod
    def main():
        """Main entry point for command-line execution."""
        cli = SiteManagerCLI()
        sys.exit(cli.run())
