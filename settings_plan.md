# Design Plan: Hard-Coded Settings & Defaults Overrides

This document proposes an architecture and design for the settings overrides system. The goal is to allow users to save or paste in common configuration patterns, pre-filling forms (such as the "Add Site" form) to eliminate repetitive typing.

## Use Case & Original Thinking
When managing dozens of WordPress sites, certain server architectures share identical configurations (e.g., standard SSH username `ubuntu`, SSH port `22`, DB host `localhost` or `127.0.0.1`, WP-CLI located at `/usr/local/bin/wp`).
Rather than re-entering these values for every single site, users should be able to:
1. Paste in a saved block of defaults.
2. Select from pre-configured "environment profiles" when adding a new site.
3. Automatically pre-fill fields based on simple matching rules.

---

## 1. Storage & Data Structure
We can leverage a dedicated configuration file `config/settings_override.json` (separated from the database/sites configuration) containing structured defaults and override rules:

```json
{
  "defaults": {
    "ssh_port": 22,
    "ssh_user": "ubuntu",
    "db_host": "localhost",
    "wp_path": "/var/www/html",
    "wp_cli_path": "wp",
    "health_check_url_template": "https://{site_name}.com"
  },
  "profiles": {
    "aws-lightsail": {
      "ssh_user": "bitnami",
      "wp_path": "/opt/bitnami/wordpress",
      "wp_cli_path": "/opt/bitnami/wp-cli/bin/wp"
    },
    "kinsta": {
      "ssh_port": 2235,
      "ssh_user": "kinstasite",
      "wp_path": "/www/kinstasite_123/public"
    }
  },
  "rules": [
    {
      "match_domain": "*.stage.com",
      "defaults": {
        "ssh_user": "stage-user",
        "db_host": "10.0.0.5"
      }
    }
  ]
}
```

---

## 2. Proposed User Interface (UI)

### Admin Settings Tab
A dedicated textarea or structured editor in the Admin section where users can paste their settings block.

- **Import / Export**: Copy-pasteable JSON block allowing users to easily backup their defaults locally or share them across environments.
- **Visual JSON Schema Validation**: Immediate validation to catch typos/formatting errors before saving.

### Add/Edit Site Form Integration
- **Default Pre-filling**: When opening the "Add Site" form, default fields (e.g., SSH Port, DB Host) are automatically pre-populated from `defaults`.
- **Profile Selector**: A dropdown at the top of the form: `Apply Template Profile`. Selecting "AWS Lightsail" immediately overrides fields with that profile's values.
- **Rule-based Auto-fill**: As the user types the health check URL or site slug, rules (like matching a domain wildcard) will dynamically pre-fill matching connection parameters in real-time.

---

## 3. Implementation Steps

1. **Backend Configuration Manager**:
   - Create `src/config/loader.py` methods to load/save `config/settings_override.json`.
   - Implement schema validation using Pydantic (`SettingsOverrideModel`).
2. **API Endpoints**:
   - `GET /api/system/settings-overrides`
   - `PUT /api/system/settings-overrides`
3. **Frontend Integration**:
   - Load overrides configuration on application bootstrap.
   - Bind default and profile values to the state in [AddSiteForm.jsx](file:///e:/ab-code-projects/projects/Wordpress/site-manager/frontend/src/components/AddSiteForm.jsx).
   - Watch form input fields and suggest auto-fill overrides when rules are triggered.
