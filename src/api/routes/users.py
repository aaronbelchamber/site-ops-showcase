import time
from flask import Blueprint, request

from src.config.loader import load_sites_config, save_sites_config, load_credentials
from src.api.auth import require_api_key
from src.api.response import ok, err
from src.api.tasks import site_operation, operation_in_progress_response

users_bp = Blueprint("users", __name__)


class UsersController:
    @staticmethod
    @require_api_key
    def list_users(site_name):
        try:
            from src.execution import get_executor
            from src.wp.cli import WPCLI
            sites = load_sites_config()
            credentials = load_credentials()
            if site_name not in sites:
                return err(f"Site '{site_name}' not found.", 404)
            site_config = sites[site_name]
            if site_config.get("status") != "Ready":
                return err(f"Site '{site_name}' is not Ready.", 400)
            with site_operation(site_name) as acquired:
                if not acquired:
                    return operation_in_progress_response(site_name)
                executor = get_executor(site_config, credentials)
                try:
                    cli = WPCLI(executor, wp_path=site_config["wp_path"], wp_cli_path=site_config.get("wp_cli_path"))
                    users = cli.list_users()
                finally:
                    executor.disconnect()

            # Record last_users_checked timestamp on site
            site_config["last_users_checked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            sites[site_name] = site_config
            save_sites_config(sites)

            return ok({
                    "users": users,
                    "last_users_checked": site_config["last_users_checked"]
                })
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def update_user_role(site_name, user_id):
        try:
            from src.execution import get_executor
            from src.wp.cli import WPCLI
            req_data = request.get_json() or {}
            role = req_data.get("role")
            if not role:
                return err("Role is required.", 400)
            sites = load_sites_config()
            credentials = load_credentials()
            site_config = sites.get(site_name)
            if not site_config or site_config.get("status") != "Ready":
                return err("Invalid site status.", 400)
            with site_operation(site_name) as acquired:
                if not acquired:
                    return operation_in_progress_response(site_name)
                executor = get_executor(site_config, credentials)
                try:
                    cli = WPCLI(executor, wp_path=site_config["wp_path"], wp_cli_path=site_config.get("wp_cli_path"))
                    success = cli.update_user_role(int(user_id), role)
                finally:
                    executor.disconnect()
            if success:
                return ok({"user_id": user_id, "role": role})
            return err("Failed to update role.", 200, data={"user_id": user_id, "role": role})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def deactivate_user(site_name, user_id):
        try:
            from src.execution import get_executor
            from src.wp.cli import WPCLI
            sites = load_sites_config()
            credentials = load_credentials()
            site_config = sites.get(site_name)
            if not site_config or site_config.get("status") != "Ready":
                return err("Invalid site status.", 400)
            with site_operation(site_name) as acquired:
                if not acquired:
                    return operation_in_progress_response(site_name)
                executor = get_executor(site_config, credentials)
                try:
                    cli = WPCLI(executor, wp_path=site_config["wp_path"], wp_cli_path=site_config.get("wp_cli_path"))
                    success = cli.deactivate_user(int(user_id))
                finally:
                    executor.disconnect()
            if success:
                return ok({"user_id": user_id, "status": "deactivated"})
            return err("Failed to deactivate user.", 200, data={"user_id": user_id, "status": "deactivated"})
        except Exception as e:
            return err(str(e), 500)

    @staticmethod
    @require_api_key
    def delete_user(site_name, user_id):
        try:
            from src.execution import get_executor
            from src.wp.cli import WPCLI
            reassign_id = request.args.get("reassign_id", type=int)
            if not reassign_id:
                return err("reassign_id query parameter is required.", 400)
            sites = load_sites_config()
            credentials = load_credentials()
            site_config = sites.get(site_name)
            if not site_config or site_config.get("status") != "Ready":
                return err("Invalid site status.", 400)
            with site_operation(site_name) as acquired:
                if not acquired:
                    return operation_in_progress_response(site_name)
                executor = get_executor(site_config, credentials)
                try:
                    cli = WPCLI(executor, wp_path=site_config["wp_path"], wp_cli_path=site_config.get("wp_cli_path"))
                    success = cli.delete_user(int(user_id), reassign_id)
                finally:
                    executor.disconnect()
            if success:
                return ok({"user_id": user_id, "deleted": True})
            return err("Failed to delete user.", 200, data={"user_id": user_id, "deleted": False})
        except Exception as e:
            return err(str(e), 500)


users_bp.route("/<site_name>/users", methods=["GET"])(UsersController.list_users)
users_bp.route("/<site_name>/users/<user_id>/role", methods=["PUT"])(UsersController.update_user_role)
users_bp.route("/<site_name>/users/<user_id>/deactivate", methods=["POST"])(UsersController.deactivate_user)
users_bp.route("/<site_name>/users/<user_id>", methods=["DELETE"])(UsersController.delete_user)
