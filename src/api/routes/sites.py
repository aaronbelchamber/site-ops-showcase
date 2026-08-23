import os
import json
import time
from flask import Blueprint, request, jsonify


from src.config.loader import (
    load_sites_config,
    save_sites_config,
    load_credentials,
    save_credentials,
    load_raw_credentials,
    load_raw_sites_config,
    mask_credential_keys,
    PROJECT_ROOT,
)
from src.api.auth import require_api_key
from src.logging.logger import logger

sites_bp = Blueprint("sites", __name__)

class SitesController:
    @staticmethod
    @require_api_key
    def get_sites():
        try:
            sites = load_sites_config()
            credentials = load_credentials()
            for name, config in sites.items():
                site_creds = credentials.get(name, {})
                masked_creds = mask_credential_keys(site_creds)
                config["ssh_private_key"] = masked_creds.get("ssh_private_key", "")

                # Attach cached update summary if available
                cache_file = os.path.join(PROJECT_ROOT, "logs", "updates", f"last_check_{name}.json")
                if os.path.exists(cache_file):
                    try:
                        with open(cache_file, "r", encoding="utf-8") as cf:
                            config["update_summary"] = json.load(cf)
                    except Exception:
                        pass
                else:
                    history_file = os.path.join(PROJECT_ROOT, "logs", "updates", f"{name}.jsonl")
                    if os.path.exists(history_file):
                        try:
                            with open(history_file, "r", encoding="utf-8") as hf:
                                lines = [line.strip() for line in hf if line.strip()]
                                if lines:
                                    last_entry = json.loads(lines[-1])
                                    if last_entry.get("timestamp"):
                                        config["update_summary"] = {
                                            "site_name": name,
                                            "timestamp": last_entry["timestamp"],
                                            "core": {"update_available": False, "details": None},
                                            "plugins": {"updates_available": False, "plugins": []},
                                            "themes": {"updates_available": False, "themes": []}
                                        }
                        except Exception:
                            pass

                # Attach cached health-check summary if available (console errors,
                # last-checked timestamp/id, overall status) for the Production Health dashboard.
                health_snapshot_file = os.path.join(PROJECT_ROOT, "logs", "health", f"last_snapshot_{name}.json")
                if os.path.exists(health_snapshot_file):
                    try:
                        with open(health_snapshot_file, "r", encoding="utf-8") as hf:
                            snapshot = json.load(hf)
                        http_check = snapshot.get("checks", {}).get("http", {})
                        console_errors = http_check.get("console_errors", [])
                        active_errors = [e for e in console_errors if e.get("severity") != "ignored"]
                        config["health_summary"] = {
                            "id": snapshot.get("id"),
                            "timestamp": snapshot.get("timestamp"),
                            "overall_status": snapshot.get("overall_status"),
                            "error_summary": http_check.get("error_summary", {}),
                            "latest_console_errors": active_errors[:3],
                        }
                    except Exception:
                        pass

            return jsonify({
                "success": True,
                "data": list(sites.values()),
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": f"Failed to retrieve sites: {e}",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def get_site(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({
                    "success": False,
                    "data": None,
                    "error": f"Site '{site_name}' not found.",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }), 404
                
            site_config = dict(sites[site_name])
            
            # Merge credentials safely
            credentials = load_credentials()
            site_creds = credentials.get(site_name, {})
            ssh_key = site_creds.get("ssh_private_key")
            if ssh_key:
                ssh_key = ssh_key.strip()
                if not ssh_key.startswith("-----BEGIN") and "\n" not in ssh_key:
                    site_config["ssh_private_key"] = ssh_key
                else:
                    site_config["ssh_private_key"] = "📄 [Stored Private Key]"
            else:
                site_config["ssh_private_key"] = ""
                
            return jsonify({
                "success": True,
                "data": site_config,
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
    def add_site():
        try:
            body = request.get_json() or {}
            site_name = body.get("site_name")
            if not site_name:
                return jsonify({"success": False, "data": None, "error": "Missing 'site_name'.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 400
                
            sites = load_sites_config()
            if site_name in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' already exists.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 409
                
            # Parse fields
            display_name = body.get("display_name", "My WordPress Site")
            status = body.get("status", "Ready")
            credential_profile = body.get("credential_profile") or None
            ssh_host = body.get("ssh_host")
            ssh_port = int(body.get("ssh_port", 22)) if body.get("ssh_port") is not None else 22
            ssh_user = body.get("ssh_user")
            wp_path = body.get("wp_path")
            db_host = body.get("db_host", "localhost")
            db_name = body.get("db_name")
            db_user = body.get("db_user")
            wp_cli_path = body.get("wp_cli_path")
            health_check_url = body.get("health_check_url")
            include_media = bool(body.get("include_media", False))
            source = body.get("source", "local")
            domain = body.get("domain") or None
            
            # Build config object
            site_config = {
                "display_name": display_name,
                "status": status,
                "credential_profile": credential_profile,
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
                "source": source,
                "domain": domain,
                "creation_source": body.get("creation_source", "manual"),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "created_by": body.get("created_by", "Admin User")
            }

            
            # Sensitive credentials
            ssh_password = body.get("ssh_password")
            ssh_private_key = body.get("ssh_private_key")
            db_password = body.get("db_password")
            
            # Copy credentials from source site if requested
            clone_from = body.get("clone_credentials_from")
            if clone_from:
                raw_creds = load_raw_credentials()
                if clone_from in raw_creds:
                    source_creds = raw_creds[clone_from]
                    if not ssh_password:
                        ssh_password = source_creds.get("ssh_password")
                    if not ssh_private_key:
                        ssh_private_key = source_creds.get("ssh_private_key")
                    if not db_password:
                        db_password = source_creds.get("db_password")

            # Validate with SiteConfigModel
            from src.config.loader import SiteConfigModel
            try:
                validation_config = dict(site_config)
                validation_config["site_name"] = site_name
                validation_config["ssh_password"] = ssh_password
                validation_config["ssh_private_key"] = ssh_private_key
                
                validated = SiteConfigModel(**validation_config)
                site_config = validated.model_dump()
            except Exception as e:
                return jsonify({"success": False, "data": None, "error": f"Validation failed: {e}", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 400
                
            # Save non-sensitive site config
            sites[site_name] = site_config
            
            # Save sensitive credentials
            credentials = load_raw_credentials()
            credentials[site_name] = {
                "ssh_password": ssh_password,
                "ssh_private_key": ssh_private_key,
                "db_password": db_password
            }
            
            save_sites_config(sites)
            save_credentials(credentials)
            logger.info(f"Site '{site_name}' successfully added (display name: '{display_name}', status: '{status}').")
            
            response_data = dict(site_config)
            response_data["site_name"] = site_name
            
            return jsonify({
                "success": True,
                "data": response_data,
                "error": None,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 201
            
        except Exception as e:
            return jsonify({
                "success": False,
                "data": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }), 500

    @staticmethod
    @require_api_key
    def update_site(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
                
            body = request.get_json() or {}
            
            # Clean current config from disk for validation
            site_config = dict(sites[site_name])
            site_config.pop("site_name", None)
            
            # Update config fields if present in body
            for field in ["display_name", "status", "credential_profile", "ssh_host", "ssh_port", "ssh_user", "wp_path", "db_host", "db_name", "db_user", "wp_cli_path", "health_check_url", "include_media", "source", "domain"]:
                if field in body:
                    if field == "ssh_port":
                        site_config[field] = int(body[field]) if body[field] is not None else 22
                    elif field == "include_media":
                        site_config[field] = bool(body[field])
                    else:
                        # Treat empty strings as None for connection fields
                        val = body[field]
                        if field in ["credential_profile", "ssh_host", "ssh_user", "wp_path", "db_name", "db_user", "wp_cli_path", "health_check_url", "domain"] and val == "":
                            val = None
                        site_config[field] = val
                        
            # Validate with SiteConfigModel
            from src.config.loader import SiteConfigModel
            try:
                validation_config = dict(site_config)
                validation_config["site_name"] = site_name
                validation_config["ssh_password"] = body.get("ssh_password")
                validation_config["ssh_private_key"] = body.get("ssh_private_key")
                
                validated = SiteConfigModel(**validation_config)
                site_config = validated.model_dump()
            except Exception as e:
                return jsonify({"success": False, "data": None, "error": f"Validation failed: {e}", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 400
                
            # Update credentials if provided
            credentials = load_raw_credentials()
            site_creds = credentials.get(site_name, {})
            cred_updated = False
            
            for cred_field in ["ssh_password", "ssh_private_key", "db_password"]:
                if cred_field in body:
                    val = body[cred_field]
                    if cred_field == "ssh_private_key" and val == "📄 [Stored Private Key]":
                        continue
                    site_creds[cred_field] = val if val != "" else None
                    cred_updated = True
                    
            if cred_updated:
                credentials[site_name] = site_creds
                save_credentials(credentials)
                
            sites[site_name] = site_config
            save_sites_config(sites)
            logger.info(f"Site '{site_name}' successfully updated (status: '{site_config.get('status')}').")
            
            response_data = dict(site_config)
            response_data["site_name"] = site_name
            
            return jsonify({
                "success": True,
                "data": response_data,
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
    def delete_site(site_name):
        try:
            sites = load_sites_config()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found.", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), 404
                
            sites.pop(site_name)
            credentials = load_raw_credentials()
            if site_name in credentials:
                credentials.pop(site_name)
                save_credentials(credentials)
                
            save_sites_config(sites)
            logger.info(f"Site '{site_name}' successfully deleted.")
            
            return jsonify({
                "success": True,
                "data": {"message": f"Site '{site_name}' successfully removed."},
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
    def scan_sites():
        try:
            from src.execution import get_executor
            from src.wp.cli import WPCLI
            from src.config.loader import CONFIG_DIR
            req_data = request.get_json(silent=True) or {}
            site_name = req_data.get("site_name")
            search_root = req_data.get("search_root")
            force_rescan = bool(req_data.get("force_rescan", False))
            target_ssh_user = req_data.get("ssh_user")
            
            cache_file = os.path.join(CONFIG_DIR, "discovered_sites.json")

            sites = load_sites_config()
            credentials = load_credentials()

            from urllib.parse import urlparse

            existing_sites_info = []
            for s_key, s_val in sites.items():
                wpath = s_val.get("wp_path", "")
                norm_p = os.path.normpath(wpath).lower().rstrip("\\/") if wpath else ""
                
                h_url = s_val.get("health_check_url", "")
                host = urlparse(h_url).netloc.lower().split(":")[0] if h_url else ""
                
                existing_sites_info.append({
                    "site_name": s_key,
                    "display_name": s_val.get("display_name", s_key),
                    "norm_path": norm_p,
                    "host": host
                })

            # Helper to enrich item with import status
            def enrich_item(item):
                scan_wpath = item.get("wp_path", "")
                norm_scan = os.path.normpath(scan_wpath).lower().rstrip("\\/") if scan_wpath else ""
                
                scan_url = item.get("url", "")
                scan_host = urlparse(scan_url).netloc.lower().split(":")[0] if scan_url else ""

                matched_site = None
                for site_info in existing_sites_info:
                    cfg_path = site_info["norm_path"]
                    cfg_host = site_info["host"]

                    # 1. Exact path match
                    if norm_scan and cfg_path and norm_scan == cfg_path:
                        matched_site = site_info
                        break
                    
                    # 2. Subdirectory / parent path match
                    if norm_scan and cfg_path and (norm_scan.startswith(cfg_path) or cfg_path.startswith(norm_scan)):
                        matched_site = site_info
                        break

                    # 3. Domain / Hostname match
                    if scan_host and cfg_host and scan_host == cfg_host:
                        matched_site = site_info
                        break

                if matched_site:
                    item["already_imported"] = True
                    item["existing_site_name"] = matched_site["site_name"]
                    item["existing_display_name"] = matched_site["display_name"]
                else:
                    item["already_imported"] = False
                    item["existing_site_name"] = None
                    item["existing_display_name"] = None
                return item

            # Collect SSH targets from configured sites
            ssh_targets = []
            seen_targets = set()
            for key, s in sites.items():
                u = s.get("ssh_user") or s.get("credential_profile") or "default"
                h = s.get("ssh_host") or "localhost"
                t_key = f"{u}@{h}"
                if t_key not in seen_targets:
                    seen_targets.add(t_key)
                    ssh_targets.append({
                        "site_name": key,
                        "ssh_user": s.get("ssh_user"),
                        "ssh_host": s.get("ssh_host"),
                        "credential_profile": s.get("credential_profile"),
                        "label": f"{u} ({h})"
                    })

            cached_scans = {}
            global_last_scanned = None

            # Attempt reading cache file if present
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                        global_last_scanned = cache_data.get("last_scanned")
                        cached_scans = cache_data.get("scans", {})
                        # Migration helper: handle old un-grouped structure if found
                        if not cached_scans and "discovered" in cache_data:
                            old_disc = cache_data.get("discovered", [])
                            first_u = "default"
                            if old_disc and old_disc[0].get("ssh_user"):
                                first_u = old_disc[0]["ssh_user"]
                            cached_scans[first_u] = {
                                "ssh_user": first_u,
                                "ssh_host": old_disc[0].get("ssh_host") if old_disc else "localhost",
                                "credential_profile": old_disc[0].get("credential_profile") if old_disc else None,
                                "baseline_site_name": old_disc[0].get("baseline_site_name") if old_disc else None,
                                "last_scanned": global_last_scanned,
                                "discovered": old_disc
                            }
                except Exception:
                    pass

            if not force_rescan and cached_scans:
                # Enrich cached items with latest sites.yaml matching
                all_discovered = []
                for user_key, scan_info in cached_scans.items():
                    scan_info["discovered"] = [enrich_item(item) for item in scan_info.get("discovered", [])]
                    all_discovered.extend(scan_info["discovered"])

                return jsonify({
                    "success": True,
                    "data": all_discovered,
                    "scans": cached_scans,
                    "ssh_targets": ssh_targets,
                    "last_scanned": global_last_scanned,
                    "cached": True,
                    "error": None,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })

            # Perform fresh scan
            # Select baseline site
            if not site_name:
                if target_ssh_user:
                    for k, s in sites.items():
                        if s.get("ssh_user") == target_ssh_user or s.get("credential_profile") == target_ssh_user:
                            site_name = k
                            break
                if not site_name and sites:
                    site_name = list(sites.keys())[0]

            if not site_name:
                return jsonify({"success": False, "data": None, "error": "No baseline site available for SSH execution."}), 400

            site_config = sites.get(site_name)
            executor = get_executor(site_config, credentials)
            wp_path = site_config.get("wp_path", "/")
            cli = WPCLI(executor, wp_path=wp_path)
            
            discovered_raw = cli.scan_server_sites(search_root=search_root)
            user_key = site_config.get("ssh_user") or site_config.get("credential_profile") or "default"
            scan_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            discovered_enriched = []
            for item in discovered_raw:
                item["baseline_site_name"] = site_name
                item["ssh_host"] = site_config.get("ssh_host")
                item["ssh_user"] = site_config.get("ssh_user")
                item["ssh_port"] = site_config.get("ssh_port", 22)
                item["credential_profile"] = site_config.get("credential_profile")
                if not item.get("db_name"):
                    item["db_name"] = site_config.get("db_name")
                if not item.get("db_user"):
                    item["db_user"] = site_config.get("db_user")
                
                enrich_item(item)
                discovered_enriched.append(item)

            cached_scans[user_key] = {
                "ssh_user": site_config.get("ssh_user"),
                "ssh_host": site_config.get("ssh_host"),
                "credential_profile": site_config.get("credential_profile"),
                "baseline_site_name": site_name,
                "last_scanned": scan_timestamp,
                "discovered": discovered_enriched
            }

            all_discovered = []
            for scan_info in cached_scans.values():
                all_discovered.extend(scan_info.get("discovered", []))

            # Save cache to disk
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "last_scanned": scan_timestamp,
                        "scans": cached_scans,
                        "discovered": all_discovered
                    }, f, indent=2)
            except Exception as cache_err:
                logger.warning(f"Failed to cache discovered sites: {cache_err}")

            return jsonify({
                "success": True,
                "data": all_discovered,
                "scans": cached_scans,
                "ssh_targets": ssh_targets,
                "last_scanned": scan_timestamp,
                "cached": False,
                "error": None,
                "timestamp": scan_timestamp
            })


        except Exception as e:
            return jsonify({"success": False, "data": None, "error": str(e)}), 500

    @staticmethod
    @require_api_key
    def list_users(site_name):
        try:
            from src.execution import get_executor
            from src.wp.cli import WPCLI
            sites = load_sites_config()
            credentials = load_credentials()
            if site_name not in sites:
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' not found."}), 404
            site_config = sites[site_name]
            if site_config.get("status") != "Ready":
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' is not Ready."}), 400
            executor = get_executor(site_config, credentials)
            cli = WPCLI(executor, wp_path=site_config["wp_path"], wp_cli_path=site_config.get("wp_cli_path"))
            users = cli.list_users()
            
            # Record last_users_checked timestamp on site
            site_config["last_users_checked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            sites[site_name] = site_config
            save_sites_config(sites)

            return jsonify({
                "success": True, 
                "data": {
                    "users": users,
                    "last_users_checked": site_config["last_users_checked"]
                }, 
                "error": None, 
                "timestamp": site_config["last_users_checked"]
            })
        except Exception as e:
            return jsonify({"success": False, "data": None, "error": str(e)}), 500

    @staticmethod
    @require_api_key
    def update_user_role(site_name, user_id):
        try:
            from src.execution import get_executor
            from src.wp.cli import WPCLI
            req_data = request.get_json() or {}
            role = req_data.get("role")
            if not role:
                return jsonify({"success": False, "data": None, "error": "Role is required."}), 400
            sites = load_sites_config()
            credentials = load_credentials()
            site_config = sites.get(site_name)
            if not site_config or site_config.get("status") != "Ready":
                return jsonify({"success": False, "data": None, "error": "Invalid site status."}), 400
            executor = get_executor(site_config, credentials)
            cli = WPCLI(executor, wp_path=site_config["wp_path"], wp_cli_path=site_config.get("wp_cli_path"))
            ok = cli.update_user_role(int(user_id), role)
            return jsonify({"success": ok, "data": {"user_id": user_id, "role": role}, "error": None if ok else "Failed to update role."})
        except Exception as e:
            return jsonify({"success": False, "data": None, "error": str(e)}), 500

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
                return jsonify({"success": False, "data": None, "error": "Invalid site status."}), 400
            executor = get_executor(site_config, credentials)
            cli = WPCLI(executor, wp_path=site_config["wp_path"], wp_cli_path=site_config.get("wp_cli_path"))
            ok = cli.deactivate_user(int(user_id))
            return jsonify({"success": ok, "data": {"user_id": user_id, "status": "deactivated"}, "error": None if ok else "Failed to deactivate user."})
        except Exception as e:
            return jsonify({"success": False, "data": None, "error": str(e)}), 500

    @staticmethod
    @require_api_key
    def delete_user(site_name, user_id):
        try:
            from src.execution import get_executor
            from src.wp.cli import WPCLI
            reassign_id = request.args.get("reassign_id", type=int)
            if not reassign_id:
                return jsonify({"success": False, "data": None, "error": "reassign_id query parameter is required."}), 400
            sites = load_sites_config()
            credentials = load_credentials()
            site_config = sites.get(site_name)
            if not site_config or site_config.get("status") != "Ready":
                return jsonify({"success": False, "data": None, "error": "Invalid site status."}), 400
            executor = get_executor(site_config, credentials)
            cli = WPCLI(executor, wp_path=site_config["wp_path"], wp_cli_path=site_config.get("wp_cli_path"))
            ok = cli.delete_user(int(user_id), reassign_id)
            return jsonify({"success": ok, "data": {"user_id": user_id, "deleted": ok}, "error": None if ok else "Failed to delete user."})
        except Exception as e:
            return jsonify({"success": False, "data": None, "error": str(e)}), 500

    @staticmethod
    @require_api_key
    def run_vulnerability_scan(site_name):
        try:
            from src.execution import get_executor
            from src.wp.cli import WPCLI
            sites = load_sites_config()
            credentials = load_credentials()
            site_config = sites.get(site_name)
            if not site_config or site_config.get("status") != "Ready":
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' is not Ready."}), 400
            executor = get_executor(site_config, credentials)
            cli = WPCLI(executor, wp_path=site_config["wp_path"], wp_cli_path=site_config.get("wp_cli_path"))
            result = cli.check_vulnerabilities()
            
            # Record timestamp and scan results in site config
            site_config["last_vulnerability_scan"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            site_config["last_vulnerability_details"] = result
            if result.get("status") == "success" and result.get("data"):
                site_config["vulnerability_status"] = "red" if len(result["data"]) > 0 else "green"
            else:
                site_config["vulnerability_status"] = "yellow"
            sites[site_name] = site_config
            save_sites_config(sites)

            return jsonify({"success": True, "data": result, "error": None, "timestamp": site_config["last_vulnerability_scan"]})

        except Exception as e:
            return jsonify({"success": False, "data": None, "error": str(e)}), 500

    @staticmethod
    @require_api_key
    def install_vulnerability_package(site_name):
        try:
            from src.execution import get_executor
            from src.wp.cli import WPCLI
            sites = load_sites_config()
            credentials = load_credentials()
            site_config = sites.get(site_name)
            if not site_config or site_config.get("status") != "Ready":
                return jsonify({"success": False, "data": None, "error": f"Site '{site_name}' is not Ready."}), 400
            
            executor = get_executor(site_config, credentials)
            cli = WPCLI(executor, wp_path=site_config["wp_path"], wp_cli_path=site_config.get("wp_cli_path"))
            install_res = cli.install_vulnerability_package()
            if not install_res.success:
                raw_err = install_res.stderr or install_res.stdout or "Unknown error"
                clean_err_lines = [l for l in raw_err.splitlines() if not l.strip().startswith("PHP Warning:") and not l.strip().startswith("PHP Notice:")]
                err_msg = "\n".join(clean_err_lines).strip() or raw_err.strip()
                return jsonify({"success": False, "data": None, "error": f"Failed to install package: {err_msg}"}), 500

            
            # Automatically run vulnerability scan after successful installation
            scan_result = cli.check_vulnerabilities()
            site_config["last_vulnerability_scan"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            site_config["last_vulnerability_details"] = scan_result
            if scan_result.get("status") == "success" and scan_result.get("data"):
                site_config["vulnerability_status"] = "red" if len(scan_result["data"]) > 0 else "green"
            else:
                site_config["vulnerability_status"] = "yellow"
            sites[site_name] = site_config
            save_sites_config(sites)

            return jsonify({
                "success": True,
                "data": {
                    "install_output": install_res.stdout,
                    "scan_result": scan_result
                },
                "error": None,
                "timestamp": site_config["last_vulnerability_scan"]
            })

        except Exception as e:
            return jsonify({"success": False, "data": None, "error": str(e)}), 500


# Route mappings to SitesController
sites_bp.route("", methods=["GET"])(SitesController.get_sites)
sites_bp.route("/<site_name>", methods=["GET"])(SitesController.get_site)
sites_bp.route("", methods=["POST"])(SitesController.add_site)
sites_bp.route("/<site_name>", methods=["PUT"])(SitesController.update_site)
sites_bp.route("/<site_name>", methods=["DELETE"])(SitesController.delete_site)
sites_bp.route("/scan", methods=["POST"])(SitesController.scan_sites)
sites_bp.route("/<site_name>/users", methods=["GET"])(SitesController.list_users)
sites_bp.route("/<site_name>/users/<user_id>/role", methods=["PUT"])(SitesController.update_user_role)
sites_bp.route("/<site_name>/users/<user_id>/deactivate", methods=["POST"])(SitesController.deactivate_user)
sites_bp.route("/<site_name>/users/<user_id>", methods=["DELETE"])(SitesController.delete_user)
sites_bp.route("/<site_name>/vulnerability-scan", methods=["POST"])(SitesController.run_vulnerability_scan)
sites_bp.route("/<site_name>/vulnerability-package", methods=["POST"])(SitesController.install_vulnerability_package)


