import time
import os
from flask import Blueprint, jsonify, request
from src.api.auth import require_api_key
from src.api.tasks import BACKGROUND_TASKS
from src.config.loader import load_admin_data, save_admin_data, validate_site_name, load_admin_notes, save_admin_notes
from src.config.system_backup import SystemBackupManager
from src.logging.logger import logger

system_bp = Blueprint("system", __name__)

class SystemController:
    @staticmethod
    @require_api_key
    def get_system_status():
        """Get backend status and list of active/completed background tasks."""
        return jsonify({
            "success": True,
            "data": {
                "status": "online",
                "active_tasks_count": sum(1 for t in BACKGROUND_TASKS.values() if t["status"] == "running"),
                "total_tasks_tracked": len(BACKGROUND_TASKS),
                "tasks": list(BACKGROUND_TASKS.values())
            },
            "error": None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })

    @staticmethod
    @require_api_key
    def get_task_status(task_id):
        """Retrieve status, error, and result of a background task."""
        if task_id not in BACKGROUND_TASKS:
            return jsonify({
                "success": False,
                "data": None,
                "error": f"Task ID '{task_id}' not found.",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 404
            
        return jsonify({
            "success": True,
            "data": BACKGROUND_TASKS[task_id],
            "error": None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })

    @staticmethod
    @require_api_key
    def get_logs():
        """Retrieve the recent lines of the main application log file after automatic pruning, with search and level filters."""
        import re
        from src.logging.cleanup import CleanupManager
        
        # 1. Automatic log pruning (over 30 days or LOG_RETENTION_DAYS)
        try:
            log_retention = int(os.getenv("LOG_RETENTION_DAYS", "30"))
        except Exception:
            log_retention = 30
            
        cleanup_mgr = CleanupManager()
        cleanup_mgr.prune_app_log(log_retention)
        
        from src.logging.logger import current_month_dir
        log_path = os.path.join(current_month_dir(), "app.log")
        
        limit = int(request.args.get("limit", 100))
        filter_level = request.args.get("level", "").strip().upper()
        search_query = request.args.get("query", "").strip().lower()
        
        if not os.path.exists(log_path):
            return jsonify({
                "success": True,
                "data": {
                    "log_file_found": False,
                    "lines": [],
                    "entries": []
                },
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
            
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            # Parse all lines into structured entries
            parsed_entries = []
            log_line_regex = re.compile(r'^\[([^\]]+)\]\s+\[([^\]]+)\]\s+(.*)$')
            
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                match = log_line_regex.match(line_str)
                if match:
                    parsed_entries.append({
                        "timestamp": match.group(1),
                        "level": match.group(2),
                        "message": match.group(3)
                    })
                else:
                    if parsed_entries:
                        # Append details (like stacktrace) to the last entry
                        parsed_entries[-1]["message"] += "\n" + line_str
                    else:
                        parsed_entries.append({
                            "timestamp": "",
                            "level": "INFO",
                            "message": line_str
                        })
                        
            # Filter entries
            filtered_entries = []
            for entry in parsed_entries:
                if filter_level and entry["level"] != filter_level:
                    continue
                if search_query and search_query not in entry["message"].lower():
                    continue
                filtered_entries.append(entry)
                
            # Slice to latest limits
            sliced_entries = filtered_entries[-limit:]
            
            # Reconstruct legacy raw lines for compatibility
            legacy_lines = []
            for entry in sliced_entries:
                ts_part = f"[{entry['timestamp']}] " if entry['timestamp'] else ""
                lvl_part = f"[{entry['level']}] " if entry['level'] else ""
                legacy_lines.append(f"{ts_part}{lvl_part}{entry['message']}")
                
            return jsonify({
                "success": True,
                "data": {
                    "log_file_found": True,
                    "lines": legacy_lines,
                    "entries": sliced_entries
                },
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": f"Failed to read log file: {e}",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def get_ssh_keys():
        """Discover active SSH Agent keys and keys inside ~/.ssh folder."""
        from pathlib import Path
        from src.execution.ssh import SSHExecutor
        
        agent_active, agent_keys = SSHExecutor.get_agent_keys()
            
        ssh_dir = Path.home() / ".ssh"
        discovered_keys = []
        if ssh_dir.exists() and ssh_dir.is_dir():
            for entry in ssh_dir.iterdir():
                if entry.is_file():
                    name = entry.name
                    if name in ["known_hosts", "authorized_keys", "config", "environment"] or name.endswith(".pub"):
                         continue
                    try:
                        with open(entry, "r", encoding="utf-8", errors="ignore") as f:
                            first_line = f.readline()
                            if "PRIVATE KEY" in first_line:
                                discovered_keys.append({
                                    "name": name,
                                    "path": str(entry),
                                    "type": first_line.strip("- \n\r")
                                })
                    except Exception:
                        pass
                        
        return jsonify({
            "success": True,
            "data": {
                "agent_active": agent_active or ("SSH_AUTH_SOCK" in os.environ),
                "agent_keys": agent_keys,
                "keys": discovered_keys
            },
            "error": None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })

    @staticmethod
    @require_api_key
    def get_ssh_key_content():
        """Retrieve the content of a specific ~/.ssh private key file securely."""
        from pathlib import Path
        
        body = request.get_json() or {}
        name = body.get("name")
        if not name:
            return jsonify({"success": False, "data": None, "error": "Key name is required.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 400
            
        # Prevent path traversal
        name = os.path.basename(name)
        ssh_dir = Path.home() / ".ssh"
        key_path = ssh_dir / name
        
        if not key_path.exists() or not key_path.is_file():
            return jsonify({"success": False, "data": None, "error": f"Key file '{name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
            
        try:
            with open(key_path, "r", encoding="utf-8") as f:
                content = f.read()
            return jsonify({
                "success": True,
                "data": {
                    "name": name,
                    "content": content
                },
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception as e:
            return jsonify({"success": False, "data": None, "error": f"Failed to read key file: {e}", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 500

    @staticmethod
    @require_api_key
    def get_ssh_config():
        """Discover hosts and profiles defined in ~/.ssh/config."""
        from pathlib import Path
        from src.execution.ssh import SSHExecutor
        
        ssh_config_path = Path.home() / ".ssh" / "config"
        profiles = SSHExecutor.parse_ssh_config(str(ssh_config_path))
                
        return jsonify({
            "success": True,
            "data": {
                "profiles": profiles
            },
            "error": None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })

    @staticmethod
    @require_api_key
    def start_ssh_agent():
        """Programmatically start a user-space ssh-agent process and update os.environ."""
        from src.execution.local import LocalExecutor
        import re
        import platform
        from pathlib import Path
        
        # Determine the ssh-agent command to run
        ssh_agent_cmd = "ssh-agent -s"
        if platform.system() == "Windows":
            # Prefer Git's ssh-agent.exe because it runs in user-space and does not require the system service to be enabled
            default_paths = [
                Path(os.environ.get("SystemDrive", "C:")) / "Program Files" / "Git" / "usr" / "bin" / "ssh-agent.exe",
                Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32" / "OpenSSH" / "ssh-agent.exe",
            ]
            for path in default_paths:
                if path.exists():
                    ssh_agent_cmd = f'"{str(path)}" -s'
                    break
                    
        try:
            executor = LocalExecutor()
            result = executor.execute(ssh_agent_cmd)
            if not result.success:
                err_msg = result.stderr or result.stdout or ""
                if "1058" in err_msg or "disabled" in err_msg.lower():
                    err_msg = "The Windows OpenSSH Authentication Agent service is disabled (Error 1058). Please enable it by running 'Set-Service -Name ssh-agent -StartupType Manual' in an Administrator PowerShell first."
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": f"Failed to start ssh-agent: {err_msg}",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 500
                
            stdout = result.stdout
            
            # Parse SSH_AUTH_SOCK and SSH_AGENT_PID
            auth_sock_match = re.search(r'SSH_AUTH_SOCK=(.*?);', stdout)
            agent_pid_match = re.search(r'SSH_AGENT_PID=(\d+);', stdout)
            
            if auth_sock_match:
                sock_path = auth_sock_match.group(1).strip()
                os.environ["SSH_AUTH_SOCK"] = sock_path
                
                pid = None
                if agent_pid_match:
                    pid = agent_pid_match.group(1).strip()
                    os.environ["SSH_AGENT_PID"] = pid
                    
                return jsonify({
                    "success": True,
                    "data": {
                        "ssh_auth_sock": sock_path,
                        "ssh_agent_pid": pid
                    },
                    "error": None,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })
            else:
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": f"Failed to parse SSH_AUTH_SOCK from ssh-agent output: {stdout}",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 500
                
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": f"Failed to run ssh-agent: {e}",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def test_connection():
        """Test SSH connection using provided credentials before saving."""
        from src.execution import get_executor
        
        body = request.get_json() or {}
        site_config = body.get("site_config", {})
        credentials = body.get("credentials", {})
        
        # Resolve credential profile if provided, or site-specific credentials if site_name provided
        profile_id = site_config.get("credential_profile")
        site_name = site_config.get("site_name")
        
        from src.config.loader import load_raw_credentials
        raw_creds = load_raw_credentials()
        
        base_creds = {}
        if profile_id:
            profiles = raw_creds.get("_profiles", {})
            if profile_id in profiles:
                base_creds = profiles[profile_id]
        elif site_name:
            if site_name in raw_creds:
                base_creds = raw_creds[site_name]
                
        # Resolve host, port, user if not provided in site_config or if they are default values
        if not site_config.get("ssh_host") and "ssh_host" in base_creds:
            site_config["ssh_host"] = base_creds["ssh_host"]
        if ("ssh_port" not in site_config or site_config["ssh_port"] == 22) and "ssh_port" in base_creds:
            site_config["ssh_port"] = base_creds["ssh_port"]
        if not site_config.get("ssh_user") and "ssh_user" in base_creds:
            site_config["ssh_user"] = base_creds["ssh_user"]
            
        # Resolve password/private key from base_creds if missing or placeholders
        ssh_pass = credentials.get("ssh_password")
        if (not ssh_pass or ssh_pass == "●●●●●●●●") and "ssh_password" in base_creds:
            credentials["ssh_password"] = base_creds["ssh_password"]
            
        ssh_key = credentials.get("ssh_private_key")
        if (not ssh_key or ssh_key == "📄 [Stored Private Key]") and "ssh_private_key" in base_creds:
            credentials["ssh_private_key"] = base_creds["ssh_private_key"]
            
        # Ensure site_name is None so get_executor parses credentials dictionary directly
        site_config["site_name"] = None
        
        print(f"DEBUG test_connection site_config: {site_config}")
        print(f"DEBUG test_connection credentials: {{'ssh_password': '***' if credentials.get('ssh_password') else None, 'ssh_private_key': '***' if credentials.get('ssh_private_key') else None}}")
        
        try:
            executor = get_executor(site_config, credentials)
            connected = executor.connect()
            if not connected:
                raise ConnectionError("Failed to connect. Please check host, port, username, password, or key path.")
            
            wp_path = site_config.get("wp_path")
            wp_status = "Not checked"
            if wp_path:
                res = executor.execute(f'test -d "{wp_path}"')
                if res.success:
                    wp_status = "Valid directory path"
                else:
                    wp_status = f"Path does not exist on target host."
                    
            executor.disconnect()
            return jsonify({
                "success": True,
                "data": {
                    "message": "SSH Connection successful!",
                    "wp_path_status": wp_status
                },
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 400

    @staticmethod
    @require_api_key
    def get_admin_data():
        """Retrieve the entire admin_data.json file content."""
        try:
            data = load_admin_data()
            return jsonify({
                "success": True,
                "data": data,
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
    def update_admin_data():
        """Update non-site fields in admin_data.json, and validate site fields if provided."""
        try:
            body = request.get_json() or {}
            existing = load_admin_data()
            
            for key, val in body.items():
                if key == "sites":
                    # Validate sites schema if provided
                    validated_sites = {}
                    for s_name, s_cfg in val.items():
                        if not validate_site_name(s_name):
                            raise ValueError(f"Invalid site slug '{s_name}'. Only lowercase letters, numbers, and hyphens allowed.")
                        from src.config.loader import SiteConfigModel
                        s_cfg_copy = dict(s_cfg)
                        s_cfg_copy["site_name"] = s_name
                        validated = SiteConfigModel(**s_cfg_copy)
                        validated_sites[s_name] = validated.model_dump()
                    existing["sites"] = validated_sites
                else:
                    existing[key] = val
                    
            save_admin_data(existing)
            logger.info("Admin settings updated in admin_data.json.")
            return jsonify({
                "success": True,
                "data": existing,
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 400

    @staticmethod
    @require_api_key
    def get_notes():
        """Retrieve the admin notes plaintext content."""
        try:
            notes = load_admin_notes()
            return jsonify({
                "success": True,
                "data": {
                    "notes": notes
                },
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
    def update_notes():
        """Update the admin notes plaintext content."""
        try:
            body = request.get_json() or {}
            notes = body.get("notes", "")
            save_admin_notes(notes)
            logger.info("Admin notes updated in admin_notes.txt.")
            return jsonify({
                "success": True,
                "data": {
                    "notes": notes
                },
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
    def list_system_backups():
        """List all configuration backup files."""
        try:
            backups = SystemBackupManager.list_backups()
            return jsonify({
                "success": True,
                "data": backups,
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
    def create_system_backup():
        """Create a new backup ZIP of the configurations."""
        try:
            path = SystemBackupManager.create_backup()
            filename = os.path.basename(path)
            logger.info(f"System settings configuration backup created: '{filename}'.")
            return jsonify({
                "success": True,
                "data": {
                    "filename": filename,
                    "message": "System settings backup created successfully."
                },
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
    def restore_system_backup():
        """Restore configuration settings from a specific backup file."""
        try:
            body = request.get_json() or {}
            filename = body.get("filename")
            if not filename:
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "Filename is required.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400
            
            SystemBackupManager.restore_backup(filename)
            logger.info(f"System settings configuration restored from backup: '{filename}'.")
            return jsonify({
                "success": True,
                "data": {
                    "message": f"System settings restored successfully from '{filename}'."
                },
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
    def delete_system_backup(filename):
        """Delete a specific configuration backup file."""
        try:
            filename = os.path.basename(filename)
            SystemBackupManager.delete_backup(filename)
            logger.info(f"System settings configuration backup deleted: '{filename}'.")
            return jsonify({
                "success": True,
                "data": {
                    "message": f"Backup '{filename}' deleted successfully."
                },
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
    def download_system_backup(filename):
        """Download a specific configuration backup file."""
        try:
            filename = os.path.basename(filename)
            backup_dir = SystemBackupManager.get_backup_dir()
            path = backup_dir / filename
            if not path.exists():
                return jsonify({"success": False, "error": "Backup file not found."}), 404
            from flask import send_from_directory
            return send_from_directory(str(backup_dir), filename, as_attachment=True)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @staticmethod
    @require_api_key
    def upload_system_backup():
        """Upload a backup ZIP file and restore configuration settings from it."""
        try:
            if 'file' not in request.files:
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "No file part in the request.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400
            file = request.files['file']
            if file.filename == '':
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "No file selected.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400
            
            if file and file.filename.endswith('.zip'):
                backup_dir = SystemBackupManager.get_backup_dir()
                temp_filename = f"upload_{int(time.time())}.zip"
                temp_path = backup_dir / temp_filename
                file.save(str(temp_path))
                
                try:
                    SystemBackupManager.restore_backup(temp_filename)
                    logger.info(f"System settings configuration uploaded and restored successfully: '{file.filename}'.")
                    return jsonify({
                        "success": True,
                        "data": {
                            "message": "System settings restored successfully from uploaded file."
                        },
                        "error": None,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    })
                finally:
                    if temp_path.exists():
                        temp_path.unlink()
            else:
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "Only ZIP files are supported.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

# Export module level get_task_status for app.py mapping
get_task_status = SystemController.get_task_status

# Route mappings to SystemController
system_bp.route("/status", methods=["GET"])(SystemController.get_system_status)
system_bp.route("/tasks/<task_id>", methods=["GET"])(SystemController.get_task_status)
system_bp.route("/logs", methods=["GET"])(SystemController.get_logs)
system_bp.route("/ssh-keys", methods=["GET"])(SystemController.get_ssh_keys)
system_bp.route("/ssh-key-content", methods=["POST"])(SystemController.get_ssh_key_content)
system_bp.route("/ssh-config", methods=["GET"])(SystemController.get_ssh_config)
system_bp.route("/ssh-agent/start", methods=["POST"])(SystemController.start_ssh_agent)
system_bp.route("/test-connection", methods=["POST"])(SystemController.test_connection)
system_bp.route("/admin-data", methods=["GET"])(SystemController.get_admin_data)
system_bp.route("/admin-data", methods=["PUT"])(SystemController.update_admin_data)
system_bp.route("/notes", methods=["GET"])(SystemController.get_notes)
system_bp.route("/notes", methods=["PUT"])(SystemController.update_notes)
system_bp.route("/backups", methods=["GET"])(SystemController.list_system_backups)
system_bp.route("/backups/create", methods=["POST"])(SystemController.create_system_backup)
system_bp.route("/backups/restore", methods=["POST"])(SystemController.restore_system_backup)
system_bp.route("/backups/<filename>", methods=["DELETE"])(SystemController.delete_system_backup)
system_bp.route("/backups/<filename>/download", methods=["GET"])(SystemController.download_system_backup)
system_bp.route("/backups/upload", methods=["POST"])(SystemController.upload_system_backup)
