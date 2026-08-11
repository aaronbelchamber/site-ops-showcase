import time
import re
import uuid
from flask import Blueprint, request, jsonify
from src.config.loader import (
    load_raw_credentials,
    save_credentials,
    mask_credential_keys,
)
from src.api.auth import require_api_key
from src.logging.logger import logger

profiles_bp = Blueprint("profiles", __name__)

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip("-")

class ProfilesController:
    @staticmethod
    @require_api_key
    def get_profiles():
        try:
            raw = load_raw_credentials()
            profiles_dict = raw.get("_profiles", {})
            
            # Format profiles for safe list display
            safe_profiles = []
            for p_id, p_data in profiles_dict.items():
                profile = {
                    "id": p_id,
                    "title": p_data.get("title", p_id),
                    "ssh_host": p_data.get("ssh_host", ""),
                    "ssh_port": p_data.get("ssh_port", 22),
                    "ssh_user": p_data.get("ssh_user", ""),
                    "has_password": bool(p_data.get("ssh_password")),
                    "has_private_key": bool(p_data.get("ssh_private_key"))
                }
                
                # Add safe placeholders for UI
                if p_data.get("ssh_password"):
                    profile["ssh_password"] = "●●●●●●●●"
                else:
                    profile["ssh_password"] = ""
                    
                masked_data = mask_credential_keys(p_data)
                profile["ssh_private_key"] = masked_data.get("ssh_private_key", "")
                    
                safe_profiles.append(profile)
                
            return jsonify({
                "success": True,
                "data": safe_profiles,
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
    def save_profile():
        try:
            body = request.get_json() or {}
            title = body.get("title")
            title = str(title).strip() if title is not None else ""
            if not title:
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": "Profile title is required.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 400

            p_id = body.get("id")
            if p_id is not None:
                p_id = str(p_id).strip()
            if not p_id:
                p_id = slugify(title)
                if not p_id:
                    p_id = str(uuid.uuid4().hex[:8])
            
            raw = load_raw_credentials()
            profiles_dict = raw.setdefault("_profiles", {})
            
            # Fetch existing profile if updating
            existing = profiles_dict.get(p_id, {})
            
            ssh_host = body.get("ssh_host")
            ssh_host = str(ssh_host).strip() if ssh_host is not None else ""
            
            ssh_port_val = body.get("ssh_port")
            if ssh_port_val is None or ssh_port_val == "":
                ssh_port = 22
            else:
                try:
                    ssh_port = int(ssh_port_val)
                except ValueError:
                    ssh_port = 22
                    
            ssh_user = body.get("ssh_user")
            ssh_user = str(ssh_user).strip() if ssh_user is not None else ""
            
            ssh_password = body.get("ssh_password")
            ssh_password = str(ssh_password) if ssh_password is not None else ""
            # Preserve existing password if placeholder or empty is sent in update
            if ssh_password == "●●●●●●●●" or not ssh_password:
                ssh_password = existing.get("ssh_password", "")
                
            ssh_private_key = body.get("ssh_private_key")
            ssh_private_key = str(ssh_private_key) if ssh_private_key is not None else ""
            # Preserve existing private key if placeholder or empty is sent in update
            if ssh_private_key == "📄 [Stored Private Key]" or not ssh_private_key:
                ssh_private_key = existing.get("ssh_private_key", "")
                
            # Save updated profile data
            profiles_dict[p_id] = {
                "title": title,
                "ssh_host": ssh_host,
                "ssh_port": ssh_port,
                "ssh_user": ssh_user,
                "ssh_password": ssh_password,
                "ssh_private_key": ssh_private_key
            }
            
            save_credentials(raw)
            logger.info(f"Credential profile '{title}' (ID: '{p_id}') successfully saved.")
            
            return jsonify({
                "success": True,
                "data": {
                    "id": p_id,
                    "title": title,
                    "ssh_host": ssh_host,
                    "ssh_port": ssh_port,
                    "ssh_user": ssh_user,
                    "has_password": bool(ssh_password),
                    "has_private_key": bool(ssh_private_key)
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
    def delete_profile(profile_id):
        try:
            raw = load_raw_credentials()
            profiles_dict = raw.get("_profiles", {})
            if profile_id in profiles_dict:
                del profiles_dict[profile_id]
                save_credentials(raw)
                logger.info(f"Credential profile '{profile_id}' successfully deleted.")
                
            return jsonify({
                "success": True,
                "data": None,
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

# Route mappings
profiles_bp.route("", methods=["GET"])(ProfilesController.get_profiles)
profiles_bp.route("", methods=["POST"])(ProfilesController.save_profile)
profiles_bp.route("/<profile_id>", methods=["DELETE"])(ProfilesController.delete_profile)
