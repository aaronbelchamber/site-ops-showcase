# 🚀 WordPress Site Manager

> Built by [Aaron Belchamber](https://belchamber.us) — Business Growth & Cloud Systems Architect
> A standalone infrastructure management tool — no dependency on any other project.
> More: [Brandager.com](https://brandager.com) · [Belchamber.us](https://belchamber.us) · [Tools.Belchamber.us](https://tools.belchamber.us)

A powerful, local-first dashboard & CLI orchestrator for managing multi-site WordPress infrastructure. Perform bulk updates with pre/post transaction health checks, automated database & file rollbacks, vulnerability scanning, and encrypted credential storage.

---

## Why This Exists

Running updates across a handful of client WordPress sites by hand doesn't scale, and it's exactly the kind of workflow where a failed update can take a site down with no easy way back. This tool automates the parts that are tedious (checking every site, applying updates one by one) and the parts that are risky (no backup before an update, no verification after) — so bulk maintenance across a whole portfolio of sites becomes a single command instead of an afternoon of careful, nervous clicking.

It's also a practical demonstration of how I build infrastructure tooling: a transactional update engine with automatic rollback, encrypted-at-rest credential storage instead of plaintext config, and a clean separation between the orchestration backend and the dashboard UI.

---

## ✨ Key Features

- **🌐 Multi-Site Dashboard**: Manage remote (SSH) and local WordPress instances from a single, modern UI.
- **🛡️ Transactional Update Engine**:
  - Automatically runs pre-update health checks.
  - Takes database & file backups before applying updates.
  - Performs post-update health & visual checks.
  - **Auto-Rollback**: Automatically restores database & file state if post-update verification fails!
- **🔒 Encrypted Credential Security**: AES-256 Fernet encryption at rest for all SSH passwords, private keys, and DB credentials.
- **☁️ Automated Google Drive Backups**: Seamlessly syncs timestamped system configuration backups to your Google Drive folder.
- **🔍 WP-CLI Vulnerability Scanning**: Integrated WP-CLI vulnerability checks for WordPress Core, installed themes, and plugins.
- **📊 Visual Regression & Health Monitoring**: Continuous HTTP health checks, WP API status, and screenshot diff comparisons.

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite SPA |
| Backend | Flask (Python) REST API |
| Site connectivity | SSH (Paramiko) + WP-CLI abstraction layer |
| Credential storage | AES-256 Fernet encryption at rest |
| Backup sync | Google Drive API |
| Testing | pytest |

---

## ⚡ Quick Start

### 1. Installation
Clone the repository and install backend & frontend dependencies:

```bash
# Clone the repository
git clone https://github.com/aaronbelchamber/wordpress-site-manager.git
cd wordpress-site-manager

# Install Python requirements
pip install -r requirements.txt

# Copy environment template
cp config/.env.example config/.env
cp config/sites.yaml.example config/sites.yaml

# Generate secret encryption key
python manage.py init
```

### 2. Google Drive Backup Wizard Setup
Automate your configuration backups by linking your Google Drive folder:

```bash
python manage.py setup-gdrive
```
*Follow the interactive prompt to set and verify your Google Drive sync path.*

### 3. Launching the Application
Start the backend server:

```bash
python manage.py runserver
```
Open **`http://127.0.0.1:5000`** in your browser.

---

## 🏗️ Architecture & Security Model

```
 ┌─────────────────────────────────────────────────────────┐
 │                   Vite + React SPA                      │
 └────────────────────────────┬────────────────────────────┘
                              │ REST API (/api/*)
 ┌────────────────────────────▼────────────────────────────┐
 │                     Flask API Backend                   │
 ├─────────────────────────────────────────────────────────┤
 │  - SystemBackupManager (Auto Google Drive Sync)         │
 │  - Transactional Update & Health Check Engine           │
 │  - WP-CLI Abstraction & SSH Executor Layer               │
 └────────────────────────────┬────────────────────────────┘
                              │ Encrypted at rest (Fernet)
 ┌────────────────────────────▼────────────────────────────┐
 │              ~/.wp_site_manager/credentials.enc         │
 └─────────────────────────────────────────────────────────┘
```

- **Local-First**: Zero external cloud dependency or subscription fees.
- **Security-First**: Sensitive passwords and SSH keys are stored in encrypted form on disk (`credentials.enc`) and decrypted in-memory only when executing operations.

---

## 🛠️ Developer Commands

| Command | Description |
|---|---|
| `python manage.py init` | Initialize directory structure & encryption key |
| `python manage.py setup-gdrive` | Run interactive Google Drive setup wizard |
| `python manage.py add-site` | Interactive CLI site wizard |
| `python manage.py list-sites` | Display configured WordPress sites |
| `python manage.py test-connection` | Verify SSH, WP-CLI, & DB connectivity |
| `python manage.py runserver` | Launch Flask API backend on port 5000 |
| `pytest` | Execute full backend test suite |

---

## 📜 License

Distributed under the [MIT License](LICENSE).
