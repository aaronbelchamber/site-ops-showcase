import os
import re
import yaml
import json
from urllib.parse import urlparse
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError
import dotenv

from src.config.crypto import CredentialEncryptor

# Determine standard directories relative to this file
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(SRC_DIR)
CONFIG_DIR = os.getenv("SITE_MANAGER_CONFIG_DIR", os.path.join(PROJECT_ROOT, "config"))
SITES_YAML_PATH = os.path.join(CONFIG_DIR, "sites.yaml")
ADMIN_DATA_JSON_PATH = os.path.join(CONFIG_DIR, "admin_data.json")
ADMIN_NOTES_TXT_PATH = os.path.join(CONFIG_DIR, "admin_notes.txt")
CREDENTIALS_ENC_PATH = os.path.expanduser("~/.wp_site_manager/credentials.enc")
ENV_PATH = os.path.join(os.getenv("SITE_MANAGER_CONFIG_DIR", os.path.join(PROJECT_ROOT, "config")), ".env")

# Load environment variables
if os.path.exists(ENV_PATH):
    dotenv.load_dotenv(ENV_PATH)

# Slug regex for site name validation: only lowercase letters, numbers, and hyphens
SLUG_REGEX = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

class SiteConfigModel(BaseModel):
    display_name: str
    status: str = "Ready"  # "Ready", "In Progress", "Archived"
    credential_profile: Optional[str] = None
    ssh_host: Optional[str] = None
    ssh_port: int = 22
    ssh_user: Optional[str] = None
    wp_path: Optional[str] = None
    db_host: str = "localhost"
    db_name: Optional[str] = None
    db_user: Optional[str] = None
    wp_cli_path: Optional[str] = None
    health_check_url: Optional[str] = None
    include_media: bool = False
    source: Optional[str] = "local"
    domain: Optional[str] = None
    creation_source: Optional[str] = "manual"
    created_at: Optional[str] = None
    created_by: Optional[str] = "Admin User"
    last_users_checked: Optional[str] = None
    last_vulnerability_scan: Optional[str] = None
    vulnerability_status: Optional[str] = None
    last_vulnerability_details: Optional[Dict[str, Any]] = None
    site_name: Optional[str] = Field(None, exclude=True)

    ssh_password: Optional[str] = Field(None, exclude=True)
    ssh_private_key: Optional[str] = Field(None, exclude=True)


    @field_validator('health_check_url')
    @classmethod
    def validate_health_check_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError('health_check_url must start with http:// or https://')
        return v

    @model_validator(mode='after')
    def validate_status_requirements(self) -> 'SiteConfigModel':
        if self.status == "Ready":
            # Determine if the host is local or remote
            host = self.ssh_host
            if not host and self.credential_profile:
                # Load profile ssh_host safely
                raw_creds = SiteConfigManager.load_raw_credentials()
                profiles = raw_creds.get("_profiles", {})
                if self.credential_profile in profiles:
                    host = profiles[self.credential_profile].get("ssh_host")
            
            # Normalize host
            host_normalized = str(host).strip().lower() if host else ""
            is_local = host_normalized in ["localhost", "127.0.0.1"]

            if self.credential_profile:
                required_fields = {
                    "wp_path": self.wp_path,
                    "db_name": self.db_name,
                    "db_user": self.db_user,
                    "health_check_url": self.health_check_url
                }
            else:
                if is_local:
                    required_fields = {
                        "wp_path": self.wp_path,
                        "db_name": self.db_name,
                        "db_user": self.db_user,
                        "health_check_url": self.health_check_url
                    }
                else:
                    required_fields = {
                        "ssh_host": self.ssh_host,
                        "ssh_user": self.ssh_user,
                        "wp_path": self.wp_path,
                        "db_name": self.db_name,
                        "db_user": self.db_user,
                        "health_check_url": self.health_check_url
                    }
            missing = [k for k, v in required_fields.items() if not v]
            if missing:
                raise ValueError(f"For status 'Ready', the following fields are required: {', '.join(missing)}")
                
            # If the host is not local, we require credentials
            if not is_local:
                has_creds = False
                # Check if credentials are passed in the model
                if self.ssh_password or self.ssh_private_key:
                    has_creds = True
                else:
                    # Load existing raw credentials from file safely
                    raw_creds = SiteConfigManager.load_raw_credentials()
                    
                    # Check site-specific credentials
                    if self.site_name and self.site_name in raw_creds:
                        site_creds = raw_creds[self.site_name]
                        if site_creds.get("ssh_password") or site_creds.get("ssh_private_key"):
                            has_creds = True
                    
                    # Check credential profile
                    if not has_creds and self.credential_profile:
                        profiles = raw_creds.get("_profiles", {})
                        if self.credential_profile in profiles:
                            profile = profiles[self.credential_profile]
                            if profile.get("ssh_password") or profile.get("ssh_private_key"):
                                has_creds = True
                
                if not has_creds:
                    raise ValueError("For status 'Ready', SSH credentials (password or private key) are required.")
        return self

class SiteConfigManager:
    @staticmethod
    def validate_site_name(site_name: str) -> bool:
        """Validate that the site name is a URL-friendly slug."""
        return bool(SLUG_REGEX.match(site_name))

    @staticmethod
    def get_encryption_key() -> str:
        """Retrieve the ENCRYPTION_KEY environment variable."""
        key = os.getenv("ENCRYPTION_KEY")
        if not key:
            raise ValueError(
                "ENCRYPTION_KEY environment variable is not set. "
                "Please check your .env file."
            )
        return key

    @staticmethod
    def get_site_domain(config: Dict[str, Any]) -> str:
        """Normalize and extract the domain name from config."""
        domain = ""
        if config.get("domain"):
            domain = str(config["domain"]).strip().lower()
        else:
            url = config.get("health_check_url")
            if url:
                try:
                    parsed = urlparse(url)
                    netloc = parsed.netloc or parsed.path
                    domain = netloc
                except Exception:
                    pass
            if not domain:
                ssh_host = config.get("ssh_host")
                if ssh_host:
                    domain = ssh_host
                    
        if domain:
            # Strip port
            domain = domain.split(':')[0]
            # Strip www.
            if domain.startswith("www."):
                domain = domain[4:]
            return domain.lower()
            
        return ""

    @staticmethod
    def mask_credential_keys(config_or_creds: Dict[str, Any]) -> Dict[str, Any]:
        """Format or mask sensitive SSH private key output for safe presentation."""
        updated = dict(config_or_creds)
        ssh_key = updated.get("ssh_private_key")
        if ssh_key:
            ssh_key = ssh_key.strip()
            if not ssh_key.startswith("-----BEGIN") and "\n" not in ssh_key:
                updated["ssh_private_key"] = ssh_key
            else:
                updated["ssh_private_key"] = "📄 [Stored Private Key]"
        else:
            updated["ssh_private_key"] = ""
        return updated

    @classmethod
    def load_admin_data(cls) -> Dict[str, Any]:
        """Load the versioned JSON admin data file."""
        if not os.path.exists(ADMIN_DATA_JSON_PATH):
            return {"sites": {}, "admin_notes": "", "global_settings": {}}
            
        with open(ADMIN_DATA_JSON_PATH, "r", encoding="utf-8") as f:
            try:
                content = f.read().strip()
                if not content:
                    return {"sites": {}, "admin_notes": "", "global_settings": {}}
                return json.loads(content) or {}
            except Exception as e:
                raise ValueError(f"Failed to parse JSON admin file: {e}")

    @classmethod
    def save_admin_data(cls, data: Dict[str, Any]) -> None:
        """Save admin data back to config/admin_data.json."""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(ADMIN_DATA_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load_admin_notes(cls) -> str:
        """Load the admin notes from admin_notes.txt, with one-time migration from admin_data.json if needed."""
        if os.path.exists(ADMIN_NOTES_TXT_PATH):
            with open(ADMIN_NOTES_TXT_PATH, "r", encoding="utf-8") as f:
                return f.read()
                
        # One-time migration: check if notes exist in admin_data.json
        if os.path.exists(ADMIN_DATA_JSON_PATH):
            try:
                admin_data = cls.load_admin_data()
                admin_notes = admin_data.get("admin_notes")
                if admin_notes:
                    # Write to the new txt file
                    cls.save_admin_notes(admin_notes)
                    
                    # Clean up admin_notes in admin_data.json
                    if "admin_notes" in admin_data:
                        del admin_data["admin_notes"]
                        cls.save_admin_data(admin_data)
                        
                    return admin_notes
            except Exception:
                pass
                
        return ""

    @classmethod
    def save_admin_notes(cls, notes: str) -> None:
        """Save admin notes back to config/admin_notes.txt."""
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(ADMIN_NOTES_TXT_PATH, "w", encoding="utf-8") as f:
            f.write(notes)

    @classmethod
    def load_raw_sites_config(cls) -> Dict[str, Any]:
        """
        Parse, validate, and merge sites.yaml and admin_data.json without resolving profiles.
        """
        # 1. Load local YAML config
        local_sites = {}
        if os.path.exists(SITES_YAML_PATH):
            with open(SITES_YAML_PATH, "r", encoding="utf-8") as f:
                try:
                    data = yaml.safe_load(f) or {}
                except yaml.YAMLError as e:
                    raise ValueError(f"Failed to parse YAML file: {e}")
                    
            sites = data.get("sites", {}) or {}
            for site_name, config in sites.items():
                if not cls.validate_site_name(site_name):
                    raise ValueError(
                        f"Invalid site name '{site_name}'. "
                        f"Site name must be a slug containing only lowercase letters, numbers, and hyphens."
                    )
                try:
                    config_copy = dict(config)
                    config_copy["site_name"] = site_name
                    validated = SiteConfigModel(**config_copy)
                    config_dict = validated.model_dump()
                    config_dict["site_name"] = site_name
                    config_dict["source"] = "local"
                    local_sites[site_name] = config_dict
                except (ValidationError, ValueError) as e:
                    if config.get("status") == "Ready":
                        try:
                            fallback_config = dict(config)
                            fallback_config["status"] = "In Progress"
                            fallback_config["site_name"] = site_name
                            validated = SiteConfigModel(**fallback_config)
                            config_dict = validated.model_dump()
                            config_dict["site_name"] = site_name
                            config_dict["source"] = "local"
                            local_sites[site_name] = config_dict
                            import logging
                            logging.getLogger("app").warning(
                                f"Site '{site_name}' failed validation as 'Ready' (error: {e}). "
                                f"Coercing status to 'In Progress'."
                            )
                            continue
                        except Exception:
                            pass
                    raise ValueError(f"Configuration validation failed for site '{site_name}': {e}")
                    
        # 2. Load JSON config
        json_sites = {}
        admin_data = cls.load_admin_data()
        sites_data = admin_data.get("sites", {}) or {}
        for site_name, config in sites_data.items():
            if not cls.validate_site_name(site_name):
                raise ValueError(
                    f"Invalid JSON site name '{site_name}'. "
                    f"Site name must be a slug containing only lowercase letters, numbers, and hyphens."
                )
            try:
                config_copy = dict(config)
                config_copy["site_name"] = site_name
                validated = SiteConfigModel(**config_copy)
                config_dict = validated.model_dump()
                config_dict["site_name"] = site_name
                config_dict["source"] = "json"
                json_sites[site_name] = config_dict
            except (ValidationError, ValueError) as e:
                if config.get("status") == "Ready":
                    try:
                        fallback_config = dict(config)
                        fallback_config["status"] = "In Progress"
                        fallback_config["site_name"] = site_name
                        validated = SiteConfigModel(**fallback_config)
                        config_dict = validated.model_dump()
                        config_dict["site_name"] = site_name
                        config_dict["source"] = "json"
                        json_sites[site_name] = config_dict
                        import logging
                        logging.getLogger("app").warning(
                            f"Site '{site_name}' failed validation as 'Ready' (error: {e}). "
                            f"Coercing status to 'In Progress'."
                        )
                        continue
                    except Exception:
                        pass
                raise ValueError(f"Configuration validation failed for JSON site '{site_name}': {e}")
                
        # 3. Merge with local precedence
        local_domains = set()
        for s_name, s_cfg in local_sites.items():
            dom = cls.get_site_domain(s_cfg)
            if dom:
                local_domains.add(dom)
                
        merged_sites = dict(local_sites)
        
        for s_name, s_cfg in json_sites.items():
            # Precedence check by domain name
            json_dom = cls.get_site_domain(s_cfg)
            if json_dom and json_dom in local_domains:
                continue
            # Precedence check by slug name
            if s_name in merged_sites:
                continue
            merged_sites[s_name] = s_cfg
            
        return merged_sites

    @classmethod
    def load_sites_config(cls) -> Dict[str, Any]:
        """
        Parse, validate, merge, and resolve credential profiles for site configs.
        """
        raw_sites = cls.load_raw_sites_config()
        
        # Load raw credentials to get profiles
        raw_creds = cls.load_raw_credentials()
        profiles = raw_creds.get("_profiles", {})
        
        resolved_sites = {}
        for site_name, site_config in raw_sites.items():
            cfg = dict(site_config)
            profile_id = cfg.get("credential_profile")
            if profile_id and profile_id in profiles:
                profile = profiles[profile_id]
                # Inherit/merge fields if not explicitly overridden on the site config
                if not cfg.get("ssh_host") and "ssh_host" in profile:
                    cfg["ssh_host"] = profile["ssh_host"]
                if ("ssh_port" not in cfg or cfg.get("ssh_port") == 22 or cfg.get("ssh_port") is None) and "ssh_port" in profile:
                    cfg["ssh_port"] = profile["ssh_port"]
                if not cfg.get("ssh_user") and "ssh_user" in profile:
                    cfg["ssh_user"] = profile["ssh_user"]
            resolved_sites[site_name] = cfg
            
        return resolved_sites

    @classmethod
    def load_raw_credentials(cls) -> Dict[str, Any]:
        """
        Decrypt and load the raw dictionary directly from credentials.enc.
        """
        if not os.path.exists(CREDENTIALS_ENC_PATH):
            return {}
            
        encryption_key = cls.get_encryption_key()
        with open(CREDENTIALS_ENC_PATH, "rb") as f:
            encrypted_bytes = f.read()
            
        if not encrypted_bytes:
            return {}
            
        try:
            return CredentialEncryptor.decrypt_credentials(encrypted_bytes, encryption_key)
        except Exception as e:
            import logging
            logging.getLogger("app").warning(f"Failed to decrypt credentials: {e}. Falling back to empty configuration.")
            return {}

    @classmethod
    def load_credentials(cls) -> Dict[str, Dict[str, Any]]:
        """
        Decrypt and load credentials.enc, resolving credential profiles for each site.
        """
        raw = cls.load_raw_credentials()
        profiles = raw.get("_profiles", {})
        
        # To avoid infinite recursion, we load the raw sites configuration
        sites = cls.load_raw_sites_config()
        
        resolved = {}
        for key, val in raw.items():
            if key != "_profiles":
                resolved[key] = dict(val)
                
        for site_name, site_config in sites.items():
            profile_id = site_config.get("credential_profile")
            if profile_id and profile_id in profiles:
                profile = profiles[profile_id]
                site_creds = resolved.setdefault(site_name, {})
                if "ssh_password" not in site_creds and "ssh_password" in profile:
                    site_creds["ssh_password"] = profile["ssh_password"]
                if "ssh_private_key" not in site_creds and "ssh_private_key" in profile:
                    site_creds["ssh_private_key"] = profile["ssh_private_key"]
                    
        return resolved

    @classmethod
    def save_credentials(cls, data: Dict[str, Dict[str, Any]]) -> None:
        """
        Encrypt and save credentials to credentials.enc.
        """
        encryption_key = cls.get_encryption_key()
        encrypted_bytes = CredentialEncryptor.encrypt_credentials(data, encryption_key)
        
        # Ensure credentials directory exists
        os.makedirs(os.path.dirname(CREDENTIALS_ENC_PATH), exist_ok=True)
        
        with open(CREDENTIALS_ENC_PATH, "wb") as f:
            f.write(encrypted_bytes)

    @classmethod
    def save_sites_config(cls, sites: Dict[str, Any]) -> None:
        """
        Save configurations back to sites.yaml (local) and admin_data.json (versioned).
        """
        local_sites = {}
        json_sites = {}
        
        # Load raw credentials to get profiles for de-duplication
        raw_creds = cls.load_raw_credentials()
        profiles = raw_creds.get("_profiles", {})
        
        for site_name, config in sites.items():
            cfg = dict(config)
            cfg.pop("site_name", None)
            cfg.pop("ssh_password", None)
            cfg.pop("ssh_private_key", None)
            
            # De-duplicate inherited fields if credential_profile is used
            profile_id = cfg.get("credential_profile")
            if profile_id and profile_id in profiles:
                profile = profiles[profile_id]
                if cfg.get("ssh_host") == profile.get("ssh_host"):
                    cfg.pop("ssh_host", None)
                if cfg.get("ssh_port") == profile.get("ssh_port"):
                    cfg.pop("ssh_port", None)
                if cfg.get("ssh_user") == profile.get("ssh_user"):
                    cfg.pop("ssh_user", None)
                    
            source = cfg.get("source", "local")
            if source == "json":
                json_sites[site_name] = cfg
            else:
                local_sites[site_name] = cfg
                
        # Save local sites to sites.yaml
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SITES_YAML_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump({"sites": local_sites}, f, default_flow_style=False, sort_keys=False)
            
        # Save json sites to admin_data.json while preserving other fields
        admin_data = cls.load_admin_data()
        admin_data["sites"] = json_sites
        cls.save_admin_data(admin_data)

# Backward-compatible module-level aliases
validate_site_name = SiteConfigManager.validate_site_name
get_encryption_key = SiteConfigManager.get_encryption_key
get_site_domain = SiteConfigManager.get_site_domain
load_admin_data = SiteConfigManager.load_admin_data
save_admin_data = SiteConfigManager.save_admin_data
load_admin_notes = SiteConfigManager.load_admin_notes
save_admin_notes = SiteConfigManager.save_admin_notes
load_raw_sites_config = SiteConfigManager.load_raw_sites_config
load_sites_config = SiteConfigManager.load_sites_config
save_sites_config = SiteConfigManager.save_sites_config
load_raw_credentials = SiteConfigManager.load_raw_credentials
load_credentials = SiteConfigManager.load_credentials
save_credentials = SiteConfigManager.save_credentials
mask_credential_keys = SiteConfigManager.mask_credential_keys

