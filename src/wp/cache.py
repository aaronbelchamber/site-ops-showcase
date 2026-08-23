import time
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from src.wp.cli import WPCLI


class CacheManager:
    """Manages cache flushing for object caches, caching plugins, and page builders (Elementor)."""

    PLUGIN_CACHE_COMMANDS: Dict[str, List[str]] = {
        "elementor": ["elementor", "flush-css"],
        "elementor-pro": ["elementor", "flush-css"],
        "wp-rocket": ["rocket", "clean", "--confirm"],
        "litespeed-cache": ["litespeed-purge", "all"],
        "w3-total-cache": ["w3-total-cache", "flush", "all"],
        "wp-super-cache": ["super-cache", "flush"],
        "wp-fastest-cache": ["fastest-cache", "clear", "all"],
        "autoptimize": ["autoptimize", "clear"],
    }

    def __init__(self, site_config: Dict[str, Any], wp_cli: WPCLI):
        self.site_config = site_config
        self.wp_cli = wp_cli
        self.site_name = site_config.get("site_name", "")

    def get_admin_url(self) -> str:
        """Resolve the WordPress admin URL for the site."""
        base_url = self.site_config.get("health_check_url") or self.site_config.get("domain") or ""
        if not base_url:
            return "/wp-admin"
        
        parsed = urlparse(base_url)
        scheme = parsed.scheme if parsed.scheme else "https"
        netloc = parsed.netloc if parsed.netloc else parsed.path.split("/")[0]
        path = parsed.path.rstrip("/") if parsed.netloc else ""
        
        if path.endswith("/cms") or "/cms" in path:
            return f"{scheme}://{netloc}{path}/wp-admin"
        return f"{scheme}://{netloc}/wp-admin"

    def get_active_plugin_slugs(self) -> List[str]:
        """Fetch list of active plugin slugs from WP-CLI."""
        try:
            plugins = self.wp_cli.list_plugins()
            active_slugs = []
            for plugin in plugins:
                if isinstance(plugin, dict) and plugin.get("status") == "active":
                    slug = plugin.get("name")
                    if slug:
                        active_slugs.append(slug.lower())
            return active_slugs
        except Exception:
            return []

    def update_database(self) -> Dict[str, Any]:
        """Run wp core update-db."""
        try:
            res = self.wp_cli.run_command(["core", "update-db"])
            return {
                "command": "wp core update-db",
                "success": res.success,
                "output": res.stdout.strip() if res.stdout else "",
                "error": res.stderr.strip() if res.stderr else None
            }
        except Exception as e:
            return {
                "command": "wp core update-db",
                "success": False,
                "output": "",
                "error": str(e)
            }

    def trigger_admin_init_migrations(self) -> Dict[str, Any]:
        """
        Best-effort: fire the admin_init action as an administrator.

        `wp core update-db` only runs WordPress core's own schema migration.
        Some plugins (WooCommerce, ACF Pro, etc.) gate their own DB migration
        behind admin_init, which normally only fires on a real wp-admin HTTP
        request from a logged-in admin — WP-CLI's bootstrap alone never
        triggers it. Impersonating an administrator via wp_set_current_user()
        and firing the hook directly closes that gap without needing HTTP
        credentials. Failure here should never block the update — it's a
        supplementary migration trigger, not a required step.
        """
        try:
            user_res = self.wp_cli.run_command(["user", "list", "--role=administrator", "--field=ID", "--number=1"])
            if not user_res.success or not user_res.stdout.strip():
                return {
                    "command": "admin_init trigger",
                    "success": False,
                    "output": "",
                    "error": "No administrator user found to impersonate; skipped."
                }
            admin_id = user_res.stdout.strip().splitlines()[0].strip()
            if not admin_id.isdigit():
                return {
                    "command": "admin_init trigger",
                    "success": False,
                    "output": "",
                    "error": f"Unexpected administrator ID output: {admin_id!r}"
                }

            eval_code = f"wp_set_current_user({int(admin_id)}); do_action('admin_init');"
            res = self.wp_cli.run_command(["eval", eval_code])
            return {
                "command": "admin_init trigger",
                "success": res.success,
                "output": res.stdout.strip() if res.stdout else "",
                "error": res.stderr.strip() if res.stderr else None
            }
        except Exception as e:
            return {
                "command": "admin_init trigger",
                "success": False,
                "output": "",
                "error": str(e)
            }

    def flush_object_cache(self) -> Dict[str, Any]:
        """Run wp cache flush."""
        try:
            res = self.wp_cli.run_command(["cache", "flush"])
            return {
                "target": "object-cache",
                "command": "wp cache flush",
                "success": res.success,
                "output": res.stdout.strip() if res.stdout else "",
                "error": res.stderr.strip() if res.stderr else None
            }
        except Exception as e:
            return {
                "target": "object-cache",
                "command": "wp cache flush",
                "success": False,
                "output": "",
                "error": str(e)
            }

    def flush_plugin_cache(self, plugin_slug: str, command_args: List[str]) -> Dict[str, Any]:
        """Run a specific cache-clearing command for a plugin."""
        cmd_str = f"wp {' '.join(command_args)}"
        try:
            res = self.wp_cli.run_command(command_args)
            return {
                "plugin": plugin_slug,
                "command": cmd_str,
                "success": res.success,
                "output": res.stdout.strip() if res.stdout else "",
                "error": res.stderr.strip() if res.stderr else None
            }
        except Exception as e:
            return {
                "plugin": plugin_slug,
                "command": cmd_str,
                "success": False,
                "output": "",
                "error": str(e)
            }

    def clear_all_caches(self) -> Dict[str, Any]:
        """
        Orchestrates full cache clearing lifecycle:
        1. Database update migration (wp core update-db)
        2. Best-effort admin_init trigger, for plugin DB migrations that
           gate themselves behind that hook (see trigger_admin_init_migrations)
        3. Elementor / Page builder cache flushing
        4. Active caching plugins flushing
        5. Object cache flushing (wp cache flush)
        """
        db_res = self.update_database()
        admin_init_res = self.trigger_admin_init_migrations()

        active_slugs = self.get_active_plugin_slugs()
        plugin_results: List[Dict[str, Any]] = []
        executed_plugins = set()

        for slug in active_slugs:
            if slug in self.PLUGIN_CACHE_COMMANDS and slug not in executed_plugins:
                cmd_args = self.PLUGIN_CACHE_COMMANDS[slug]
                plugin_res = self.flush_plugin_cache(slug, cmd_args)
                plugin_results.append(plugin_res)
                executed_plugins.add(slug)

        obj_cache_res = self.flush_object_cache()

        # Collect warnings / failures
        failures = []
        if not db_res["success"]:
            failures.append(f"DB update failed: {db_res.get('error') or db_res.get('output')}")
        for pres in plugin_results:
            if not pres["success"]:
                failures.append(f"Cache flush for {pres['plugin']} failed: {pres.get('error') or pres.get('output')}")
        if not obj_cache_res["success"]:
            failures.append(f"Object cache flush failed: {obj_cache_res.get('error') or obj_cache_res.get('output')}")

        has_warnings = len(failures) > 0
        admin_url = self.get_admin_url() if has_warnings else None

        return {
            "success": not has_warnings,
            "has_warnings": has_warnings,
            "database_update": db_res,
            # Best-effort; a failure here (e.g. no admin user, or nothing hooked
            # into admin_init) is normal and shouldn't count as a cache-flush warning.
            "admin_init_migrations": admin_init_res,
            "plugin_flushes": plugin_results,
            "object_cache": obj_cache_res,
            "warnings": failures if has_warnings else [],
            "admin_url": admin_url
        }
