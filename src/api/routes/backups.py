import time
from typing import Optional, Dict, Any
from flask import Blueprint, request, jsonify
from src.config.loader import load_sites_config, load_credentials
from src.execution import get_executor
from src.backup.manager import BackupManager
from src.api.auth import require_api_key
from src.api.tasks import start_task, operation_in_progress_response

backups_bp = Blueprint("backups", __name__)

class BackupTaskRunner:
    @staticmethod
    def run_backup_task(site_name: str, description: Optional[str] = None, include_media: Optional[bool] = None) -> Dict[str, Any]:
        sites = load_sites_config()
        site_config = sites[site_name]
        credentials = load_credentials()
        executor = get_executor(site_config, credentials)
        try:
            mgr = BackupManager(site_config, credentials, executor)
            return mgr.create_backup(description, include_media=include_media)
        finally:
            executor.disconnect()

    @staticmethod
    def run_restore_task(site_name: str, backup_id: str):
        sites = load_sites_config()
        site_config = sites[site_name]
        credentials = load_credentials()
        executor = get_executor(site_config, credentials)
        try:
            mgr = BackupManager(site_config, credentials, executor)
            mgr.restore_backup(backup_id)
            return {"backup_id": backup_id, "restored": True}
        finally:
            executor.disconnect()


class BackupsController:
    @staticmethod
    @require_api_key
    def get_backups(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
                
            credentials = load_credentials()
            site_config = sites[site_name]
            executor = get_executor(site_config, credentials)
            
            try:
                mgr = BackupManager(site_config, credentials, executor)
                backups = mgr.list_backups()
                return jsonify({
                    "success": True,
                    "data": backups,
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
    def create_backup(site_name):
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
            description = body.get("description", "Manual Web Backup")
            include_media = body.get("include_media", None)
            
            # Start backup task in background
            task_id = start_task(
                name=f"Backup: {site_name}",
                func=BackupTaskRunner.run_backup_task,
                site_name=site_name,
                description=description,
                include_media=include_media
            )

            if task_id is None:
                return operation_in_progress_response(site_name)

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
    def get_backup(site_name, backup_id):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404

            # Validate backup_id format early; ValueError is caught by the
            # except ValueError block below.
            BackupManager._validate_backup_id(backup_id)

            credentials = load_credentials()
            site_config = sites[site_name]
            executor = get_executor(site_config, credentials)

            try:
                mgr = BackupManager(site_config, credentials, executor)
                backups = mgr.list_backups()
                backup = next((b for b in backups if b.get("backup_id") == backup_id), None)
                if not backup:
                    return jsonify({"success": False, "data": None, "error": f"Backup '{backup_id}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
                return jsonify({
                    "success": True,
                    "data": backup,
                    "error": None,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })
            finally:
                executor.disconnect()
        except ValueError:
            return jsonify({
                "success": False,
                "data": None,
                "error": "Invalid backup_id.",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 400
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def restore_backup(site_name, backup_id):
        try:
            # Validate backup_id format early; ValueError is caught below.
            BackupManager._validate_backup_id(backup_id)

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

            # Start restore task in background
            task_id = start_task(
                name=f"Restore: {site_name} (Backup ID: {backup_id})",
                func=BackupTaskRunner.run_restore_task,
                site_name=site_name,
                backup_id=backup_id
            )

            if task_id is None:
                return operation_in_progress_response(site_name)

            return jsonify({
                "success": True,
                "data": {"task_id": task_id, "status": "running"},
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except ValueError:
            return jsonify({
                "success": False,
                "data": None,
                "error": "Invalid backup_id.",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 400
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def delete_backup(site_name, backup_id):
        try:
            # Validate backup_id format early; ValueError is caught below.
            BackupManager._validate_backup_id(backup_id)

            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404

            credentials = load_credentials()
            site_config = sites[site_name]
            executor = get_executor(site_config, credentials)

            try:
                mgr = BackupManager(site_config, credentials, executor)
                deleted = mgr.delete_backup(backup_id)
                if not deleted:
                    return jsonify({"success": False, "data": None, "error": f"Failed to delete backup '{backup_id}'. It may not exist.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
                return jsonify({
                    "success": True,
                    "data": {"message": f"Backup '{backup_id}' successfully deleted."},
                    "error": None,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })
            finally:
                executor.disconnect()
        except ValueError:
            return jsonify({
                "success": False,
                "data": None,
                "error": "Invalid backup_id.",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 400
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

# Route mappings to BackupsController
backups_bp.route("/<site_name>/backups", methods=["GET"])(BackupsController.get_backups)
backups_bp.route("/<site_name>/backups", methods=["POST"])(BackupsController.create_backup)
backups_bp.route("/<site_name>/backups/<backup_id>", methods=["GET"])(BackupsController.get_backup)
backups_bp.route("/<site_name>/backups/<backup_id>/restore", methods=["POST"])(BackupsController.restore_backup)
backups_bp.route("/<site_name>/backups/<backup_id>", methods=["DELETE"])(BackupsController.delete_backup)

# Backward-compatible references for tests/mocking
run_backup_task = BackupTaskRunner.run_backup_task
run_restore_task = BackupTaskRunner.run_restore_task
