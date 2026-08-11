from typing import Dict, Any
from src.wp.cli import WPCLI

class WPHealthCheck:
    def __init__(self, wp_cli: WPCLI):
        self.wp_cli = wp_cli

    def check_core_status(self) -> Dict[str, Any]:
        """
        Verify WordPress core checksums.
        """
        res = self.wp_cli.run_command(["core", "verify-checksums"])
        if res.success:
            return {
                "status": "pass",
                "message": "WordPress core checksums verified successfully."
            }
        else:
            error_details = res.stderr.strip() or res.stdout.strip() or "Unknown error"
            return {
                "status": "fail",
                "message": f"WordPress core checksum verification failed: {error_details}"
            }

    def check_plugin_status(self) -> Dict[str, Any]:
        """
        List plugins and check for available updates.
        """
        try:
            plugins = self.wp_cli.list_plugins()
            active_count = sum(1 for p in plugins if p.get("status") == "active")
            updates_available = sum(1 for p in plugins if p.get("update") == "available")
            
            return {
                "status": "pass",
                "active_count": active_count,
                "updates_available": updates_available,
                "total_count": len(plugins),
                "error": None
            }
        except Exception as e:
            return {
                "status": "fail",
                "active_count": 0,
                "updates_available": 0,
                "total_count": 0,
                "error": str(e)
            }

    def check_theme_status(self) -> Dict[str, Any]:
        """
        List themes and check for active theme and available updates.
        """
        try:
            themes = self.wp_cli.list_themes()
            active_theme = next((t.get("name") for t in themes if t.get("status") == "active"), "None")
            updates_available = sum(1 for t in themes if t.get("update") == "available")
            
            return {
                "status": "pass",
                "active_theme": active_theme,
                "updates_available": updates_available,
                "total_count": len(themes),
                "error": None
            }
        except Exception as e:
            return {
                "status": "fail",
                "active_theme": "None",
                "updates_available": 0,
                "total_count": 0,
                "error": str(e)
            }

    def check_database_connection(self) -> bool:
        """
        Check database connectivity via WP-CLI.
        """
        # Run a simple SQL query via WP-CLI to test connection
        res = self.wp_cli.run_command(["db", "query", "SELECT 1;"])
        return res.success

    def run_full_check(self) -> Dict[str, Any]:
        """
        Run all WP checks and return aggregated results.
        """
        # Check database connection first
        db_ok = self.check_database_connection()
        if not db_ok:
            return {
                "database_connection": "fail",
                "core_status": {"status": "fail", "message": "Database connection failed."},
                "plugins": {"status": "fail", "active_count": 0, "updates_available": 0, "total_count": 0, "error": "Database offline"},
                "themes": {"status": "fail", "active_theme": "None", "updates_available": 0, "total_count": 0, "error": "Database offline"},
                "status": "critical"
            }
            
        core = self.check_core_status()
        plugins = self.check_plugin_status()
        themes = self.check_theme_status()
        
        # Determine overall WP status
        # If core check fails, overall is degraded. If db fails, critical.
        status = "pass"
        if core.get("status") == "fail":
            status = "degraded"
            
        return {
            "database_connection": "pass",
            "core_status": core,
            "plugins": plugins,
            "themes": themes,
            "status": status
        }
