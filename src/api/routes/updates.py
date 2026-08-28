import time
import os
import json
from typing import Optional
from flask import Blueprint, request
from src.config.loader import load_sites_config, load_credentials, PROJECT_ROOT
from src.execution import get_executor
from src.wp.cli import WPCLI
from src.update.manager import UpdateManager
from src.api.auth import require_api_key
from src.api.tasks import start_task, operation_in_progress_response, site_operation
from src.api.response import ok, err

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

    @staticmethod
    def run_git_init_task(site_name: str, force: bool = False):
        sites = load_sites_config()
        site_config = {**sites[site_name], "site_name": site_name}
        credentials = load_credentials()
        executor = get_executor(site_config, credentials)
        try:
            from src.git.manager import GitManager
            git_mgr = GitManager(site_config, executor)
            return git_mgr.init_repo(force=force)
        finally:
            executor.disconnect()

    @staticmethod
    def run_git_push_task(site_name: str):
        sites = load_sites_config()
        site_config = {**sites[site_name], "site_name": site_name}
        credentials = load_credentials()
        executor = get_executor(site_config, credentials)
        try:
            from src.git.manager import GitManager
            git_mgr = GitManager(site_config, executor)
            return git_mgr.push_to_github()
        finally:
            executor.disconnect()

    @staticmethod
    def run_check_updates_task(site_name: str):
        sites = load_sites_config()
        site_config = sites[site_name]
        credentials = load_credentials()
        site_config_with_name = {**site_config, "site_name": site_name}
        executor = get_executor(site_config_with_name, credentials)
        try:
            wp_cli = WPCLI(executor, site_config["wp_path"], site_config.get("wp_cli_path"))
            mgr = UpdateManager(site_config, credentials, executor, wp_cli)
            updates_data = mgr.check_all_updates()
            mgr.save_cached_updates(updates_data)
            return updates_data
        finally:
            executor.disconnect()

class UpdatesController:
    @staticmethod
    def _is_stale(timestamp_str: Optional[str]) -> bool:
        if not timestamp_str:
            return True
        try:
            # Parse ISO timestamp like 2026-08-08T19:00:00Z or similar
            parsed_time = time.strptime(timestamp_str.split(".")[0].replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
            age_seconds = time.time() - time.mktime(parsed_time)
            return age_seconds > (24 * 3600)
        except Exception:
            return True

    @staticmethod
    @require_api_key
    def get_updates(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
                
            force = request.args.get("force", "false").lower() == "true"
            is_async = request.args.get("async", "false").lower() == "true" or request.args.get("background", "false").lower() == "true"
            
            # If not forcing a re-run, check if we have a fresh (non-stale) cache
            if not force:
                cache_file = os.path.join(PROJECT_ROOT, "logs", "updates", f"last_check_{site_name}.json")
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            cached_data = json.load(f)
                        is_stale = UpdatesController._is_stale(cached_data.get("timestamp"))
                        cached_data["is_stale"] = is_stale
                        if not is_stale:
                            return ok(cached_data)
                    except Exception:
                        # Cache read failed; continue to fallback logic
                        pass

                # If site is not Ready, we should not attempt a live check; return cached/fallback
                site_config = sites[site_name]
                if site_config.get("status", "Ready") != "Ready":
                    if os.path.exists(cache_file):
                        try:
                            with open(cache_file, "r", encoding="utf-8") as f:
                                cached_data = json.load(f)
                            cached_data["is_stale"] = UpdatesController._is_stale(cached_data.get("timestamp"))
                            return ok(cached_data)
                        except Exception:
                            # Fallback cache also corrupted; return stale indicator
                            pass
                    return ok({"is_stale": True, "site_name": site_name, "timestamp": None})

            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return err(f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.", 400)
                
            wp_path = site_config.get("wp_path")
            if not wp_path:
                return err(f"WordPress path (wp_path) is not configured for site '{site_name}'. Please edit the site configuration first.", 400)

            if is_async:
                task_id = start_task(
                    f"Check updates for {site_name}",
                    UpdateTaskRunner.run_check_updates_task,
                    site_name=site_name
                )
                if task_id is None:
                    return operation_in_progress_response(site_name)
                return ok({"task_id": task_id, "status": "running"})

            # If synchronous force=true, connect and run the updates check.
            # This opens SSH and runs WP-CLI inline, so it serialises against
            # background tasks on the same site like every other live operation.
            with site_operation(site_name) as acquired:
                if not acquired:
                    return operation_in_progress_response(site_name)

                credentials = load_credentials()
                site_config_with_name = {**site_config, "site_name": site_name}
                executor = get_executor(site_config_with_name, credentials)

                try:
                    wp_cli = WPCLI(executor, wp_path, site_config.get("wp_cli_path"))
                    mgr = UpdateManager(site_config, credentials, executor, wp_cli)
                    updates_data = mgr.check_all_updates()
                    updates_data["is_stale"] = False

                    # Save to cache
                    mgr.save_cached_updates(updates_data)

                    return ok(updates_data)
                finally:
                    executor.disconnect()
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def update_core(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
                
            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return err(f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.", 400)
                
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

            if task_id is None:
                return operation_in_progress_response(site_name)

            return ok({"task_id": task_id, "status": "running"})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def update_plugins(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
                
            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return err(f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.", 400)
                
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

            if task_id is None:
                return operation_in_progress_response(site_name)

            return ok({"task_id": task_id, "status": "running"})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def update_themes(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
                
            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return err(f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.", 400)
                
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

            if task_id is None:
                return operation_in_progress_response(site_name)

            return ok({"task_id": task_id, "status": "running"})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def update_all(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
                
            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return err(f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.", 400)
                
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

            if task_id is None:
                return operation_in_progress_response(site_name)

            return ok({"task_id": task_id, "status": "running"})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def trigger_check_updates(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
                
            site_config = sites[site_name]
            if site_config.get("status", "Ready") != "Ready":
                return err(f"Site '{site_name}' has status '{site_config.get('status', 'Ready')}'. Operations are only permitted on sites with 'Ready' status.", 400)
                
            wp_path = site_config.get("wp_path")
            if not wp_path:
                return err(f"WordPress path (wp_path) is not configured for site '{site_name}'. Please edit the site configuration first.", 400)

            task_id = start_task(
                name=f"Check updates for {site_name}",
                func=UpdateTaskRunner.run_check_updates_task,
                site_name=site_name
            )
            if task_id is None:
                return operation_in_progress_response(site_name)
            return ok({"task_id": task_id, "status": "running"})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def get_git_status(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found", 404)

            site_config = {**sites[site_name], "site_name": site_name}
            credentials = load_credentials()
            executor = get_executor(site_config, credentials)
            try:
                from src.git.manager import GitManager
                git_mgr = GitManager(site_config, executor)
                status = git_mgr.get_repo_status()
                return ok(status)
            finally:
                executor.disconnect()
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def trigger_git_init(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found", 404)

            site_config = sites[site_name]
            if site_config.get("status") != "Ready":
                return err(f"Site status is '{site_config.get('status')}', but must be 'Ready' to initialize Git.", 400)

            data = request.get_json(silent=True) or {}
            force = data.get("force", False)

            task_id = start_task(
                name=f"Initialize Git repository for {site_name}",
                func=UpdateTaskRunner.run_git_init_task,
                site_name=site_name,
                force=force
            )

            if task_id is None:
                return operation_in_progress_response(site_name)

            return ok({"task_id": task_id, "status": "running"})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def trigger_git_push(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found", 404)

            site_config = sites[site_name]
            if site_config.get("status") != "Ready":
                return err(f"Site status is '{site_config.get('status')}', but must be 'Ready' to push Git repo.", 400)

            task_id = start_task(
                name=f"Git push for {site_name}",
                func=UpdateTaskRunner.run_git_push_task,
                site_name=site_name
            )

            if task_id is None:
                return operation_in_progress_response(site_name)

            return ok({"task_id": task_id, "status": "running"})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def get_update_history(site_name):
        try:
            history_file = os.path.join(PROJECT_ROOT, "logs", "updates", f"{site_name}.jsonl")
            if not os.path.exists(history_file):
                return ok([])
                
            history = []
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            history.append(json.loads(line.strip()))
                        except Exception:
                            # Malformed history line; skip it, continue with others
                            pass
            return ok(history)
        except Exception as e:
            return err(str(e), 500)

# Route mappings (updates_bp registered with url_prefix="/api/sites" in app.py)
updates_bp.add_url_rule("/<site_name>/updates", view_func=UpdatesController.get_updates, methods=["GET"])
updates_bp.add_url_rule("/<site_name>/updates/check", view_func=UpdatesController.trigger_check_updates, methods=["POST"])
updates_bp.add_url_rule("/<site_name>/updates/core", view_func=UpdatesController.update_core, methods=["POST"])
updates_bp.add_url_rule("/<site_name>/updates/plugins", view_func=UpdatesController.update_plugins, methods=["POST"])
updates_bp.add_url_rule("/<site_name>/updates/themes", view_func=UpdatesController.update_themes, methods=["POST"])
updates_bp.add_url_rule("/<site_name>/updates/all", view_func=UpdatesController.update_all, methods=["POST"])
updates_bp.add_url_rule("/<site_name>/updates/history", view_func=UpdatesController.get_update_history, methods=["GET"])

# Git routes
updates_bp.add_url_rule("/<site_name>/git/status", view_func=UpdatesController.get_git_status, methods=["GET"])
updates_bp.add_url_rule("/<site_name>/git/init", view_func=UpdatesController.trigger_git_init, methods=["POST"])
updates_bp.add_url_rule("/<site_name>/git/push", view_func=UpdatesController.trigger_git_push, methods=["POST"])
