import time
import os
import json
from typing import Optional
from flask import Blueprint, request, jsonify
from src.config.loader import load_sites_config, load_credentials, PROJECT_ROOT
from src.execution import get_executor
from src.wp.cli import WPCLI
from src.update.manager import UpdateManager
from src.api.auth import require_api_key
from src.api.tasks import start_task

updates_bp = Blueprint("updates", __name__)

class UpdateTaskRunner:
    @staticmethod
    def run_core_update_task(site_name: str, major: bool = False, create_backup: bool = True, quality_checks: bool = True):
        sites = load_sites_config()
        site_config = sites[site_name]
        credentials = load_credentials()
        executor = get_executor(site_config, credentials)
        try:
            wp_cli = WPCLI(executor, site_config["wp_path"], site_config.get("wp_cli_path"))
            mgr = UpdateManager(site_config, credentials, executor, wp_cli)
            return mgr.update_core(major=major, create_backup=create_backup, quality_checks=quality_checks)
        finally:
            executor.disconnect()

    @staticmethod
    def run_plugins_update_task(site_name: str, plugin: Optional[str] = None, create_backup: bool = True, quality_checks: bool = True):
        sites = load_sites_config()
        site_config = sites[site_name]
        credentials = load_credentials()
        executor = get_executor(site_config, credentials)
        try:
            wp_cli = WPCLI(executor, site_config["wp_path"], site_config.get("wp_cli_path"))
            mgr = UpdateManager(site_config, credentials, executor, wp_cli)
            return mgr.update_plugins(plugin=plugin, create_backup=create_backup, quality_checks=quality_checks)
        finally:
            executor.disconnect()

    @staticmethod
    def run_themes_update_task(site_name: str, theme: Optional[str] = None, create_backup: bool = True, quality_checks: bool = True):
        sites = load_sites_config()
        site_config = sites[site_name]
        credentials = load_credentials()
        executor = get_executor(site_config, credentials)
        try:
            wp_cli = WPCLI(executor, site_config["wp_path"], site_config.get("wp_cli_path"))
            mgr = UpdateManager(site_config, credentials, executor, wp_cli)
            return mgr.update_themes(theme=theme, create_backup=create_backup, quality_checks=quality_checks)
        finally:
            executor.disconnect()

    @staticmethod
    def run_update_all_task(site_name: str, create_backup: bool = True, quality_checks: bool = True):
        sites = load_sites_config()
        site_config = sites[site_name]
        credentials = load_credentials()
        executor = get_executor(site_config, credentials)
        try:
            wp_cli = WPCLI(executor, site_config["wp_path"], site_config.get("wp_cli_path"))
            mgr = UpdateManager(site_config, credentials, executor, wp_cli)
            return mgr.update_all(create_backup=create_backup, quality_checks=quality_checks)
        finally:
            executor.disconnect()

class UpdatesController:
    @staticmethod
    @require_api_key
    def get_updates(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
                
            force = request.args.get("force", "false").lower() == "true"
            
            # If not forcing a re-run, try to load from cache first (even for non-Ready sites)
            if not force:
                cache_file = os.path.join(PROJECT_ROOT, "logs", "updates", f"last_check_{site_name}.json")
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            cached_data = json.load(f)
                        return jsonify({
                            "success": True,
                            "data": cached_data,
                            "error": None,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        })
                    except Exception:
                        pass
                
                # If cache file doesn't exist, try constructing it from the latest update history entry
                history_file = os.path.join(PROJECT_ROOT, "logs", "updates", f"{site_name}.jsonl")
                if os.path.exists(history_file):
                    latest_timestamp = None
                    try:
                        with open(history_file, "r", encoding="utf-8") as f:
                            lines = [line.strip() for line in f if line.strip()]
                            if lines:
                                last_entry = json.loads(lines[-1])
                                latest_timestamp = last_entry.get("timestamp")
                    except Exception:
                        pass

                    if latest_timestamp:
                        fallback_data = {
                            "site_name": site_name,
                            "timestamp": latest_timestamp,
                            "core": {"update_available": False, "details": None},
                            "plugins": {"updates_available": False, "plugins": []},
                            "themes": {"updates_available": False, "themes": []}
                        }
                        try:
                            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                            with open(cache_file, "w", encoding="utf-8") as cf:
                                json.dump(fallback_data, cf, indent=2)
                        except Exception:
                            pass

                        return jsonify({
                            "success": True,
                            "data": fallback_data,
                            "error": None,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        })

                # If neither cache nor history exists, return success with data: None
                return jsonify({
                    "success": True,
                    "data": None,
                    "error": None,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })

            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400
                
            wp_path = site_config.get("wp_path")
            if not wp_path:
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": f"WordPress path (wp_path) is not configured for site '{site_name}'. Please edit the site configuration first.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400

            # If force=true, connect and run the updates check
            credentials = load_credentials()
            site_config_with_name = {**site_config, "site_name": site_name}
            executor = get_executor(site_config_with_name, credentials)
            
            try:
                wp_cli = WPCLI(executor, wp_path, site_config.get("wp_cli_path"))
                mgr = UpdateManager(site_config, credentials, executor, wp_cli)
                updates_data = mgr.check_all_updates()
                
                # Save to cache
                mgr.save_cached_updates(updates_data)
                
                return jsonify({
                    "success": True,
                    "data": updates_data,
                    "error": None,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })
            finally:
                executor.disconnect()
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def update_core(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
                
            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400
                
            body = request.get_json() or {}
            major = bool(body.get("major", False))
            
            if "create_backup" in body:
                create_backup = bool(body.get("create_backup", True))
            else:
                create_backup = not bool(body.get("bypass_checks", False))

            if "quality_checks" in body:
                quality_checks = bool(body.get("quality_checks", True))
            else:
                quality_checks = not bool(body.get("bypass_checks", False))
            
            task_id = start_task(
                name=f"Update Core: {site_name}",
                func=UpdateTaskRunner.run_core_update_task,
                site_name=site_name,
                major=major,
                create_backup=create_backup,
                quality_checks=quality_checks
            )
            
            return jsonify({
                "success": True,
                "data": {"task_id": task_id, "status": "running"},
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def update_plugins(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
                
            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400
                
            body = request.get_json() or {}
            plugin = body.get("plugin")
            
            if "create_backup" in body:
                create_backup = bool(body.get("create_backup", True))
            else:
                create_backup = not bool(body.get("bypass_checks", False))

            if "quality_checks" in body:
                quality_checks = bool(body.get("quality_checks", True))
            else:
                quality_checks = not bool(body.get("bypass_checks", False))
            
            task_id = start_task(
                name=f"Update Plugins: {site_name} ({plugin or 'All'})",
                func=UpdateTaskRunner.run_plugins_update_task,
                site_name=site_name,
                plugin=plugin,
                create_backup=create_backup,
                quality_checks=quality_checks
            )
            
            return jsonify({
                "success": True,
                "data": {"task_id": task_id, "status": "running"},
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def update_themes(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
                
            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400
                
            body = request.get_json() or {}
            theme = body.get("theme")
            
            if "create_backup" in body:
                create_backup = bool(body.get("create_backup", True))
            else:
                create_backup = not bool(body.get("bypass_checks", False))

            if "quality_checks" in body:
                quality_checks = bool(body.get("quality_checks", True))
            else:
                quality_checks = not bool(body.get("bypass_checks", False))
            
            task_id = start_task(
                name=f"Update Themes: {site_name} ({theme or 'All'})",
                func=UpdateTaskRunner.run_themes_update_task,
                site_name=site_name,
                theme=theme,
                create_backup=create_backup,
                quality_checks=quality_checks
            )
            
            return jsonify({
                "success": True,
                "data": {"task_id": task_id, "status": "running"},
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def update_all(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
                
            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400
                
            body = request.get_json() or {}
            if "create_backup" in body:
                create_backup = bool(body.get("create_backup", True))
            else:
                create_backup = not bool(body.get("bypass_checks", False))

            if "quality_checks" in body:
                quality_checks = bool(body.get("quality_checks", True))
            else:
                quality_checks = not bool(body.get("bypass_checks", False))

            task_id = start_task(
                name=f"Update All: {site_name}",
                func=UpdateTaskRunner.run_update_all_task,
                site_name=site_name,
                create_backup=create_backup,
                quality_checks=quality_checks
            )
            
            return jsonify({
                "success": True,
                "data": {"task_id": task_id, "status": "running"},
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def get_update_history(site_name):
        try:
            history_file = os.path.join(PROJECT_ROOT, "logs", "updates", f"{site_name}.jsonl")
            if not os.path.exists(history_file):
                return jsonify({"success": True, "data": [], "error": None, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                
            history = []
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            history.append(json.loads(line.strip()))
                        except Exception:
                            pass
            return jsonify({"success": True, "data": history, "error": None, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        except Exception as e:
            return jsonify({"success": False, "data": None, "error": str(e), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 500

# Route mappings (updates_bp registered with url_prefix="/api/sites" in app.py)
updates_bp.add_url_rule("/<site_name>/updates", view_func=UpdatesController.get_updates, methods=["GET"])
updates_bp.add_url_rule("/<site_name>/updates/core", view_func=UpdatesController.update_core, methods=["POST"])
updates_bp.add_url_rule("/<site_name>/updates/plugins", view_func=UpdatesController.update_plugins, methods=["POST"])
updates_bp.add_url_rule("/<site_name>/updates/themes", view_func=UpdatesController.update_themes, methods=["POST"])
updates_bp.add_url_rule("/<site_name>/updates/all", view_func=UpdatesController.update_all, methods=["POST"])
updates_bp.add_url_rule("/<site_name>/updates/history", view_func=UpdatesController.get_update_history, methods=["GET"])
