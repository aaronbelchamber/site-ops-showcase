# Technical Setup

This guide is for developers setting up the WordPress Site Manager project locally.

## Prerequisites
- Python 3.11+ installed and available on the PATH
- Node.js 20+ installed for the frontend
- `git` if cloning the repository

## Backend Setup
1. Install Python dependencies in a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   If `requirements.txt` is not present, install the core packages manually:
   ```bash
   pip install flask python-dotenv paramiko pyyaml cryptography requests
   ```

2. Initialize the application data store:
   ```bash
   python manage.py init
   ```

3. Run the backend server:
   ```bash
   python manage.py runserver
   ```

## Frontend Setup
1. Install Node packages:
   ```bash
   cd frontend
   npm install
   ```

2. Start the Vite development server:
   ```bash
   npm run dev
   ```

3. Open the app in the browser at:
   ```text
   http://127.0.0.1:5173
   ```

## Local Authentication
For local browser auto-login, create `frontend/.env.local` with:
```env
VITE_API_TOKEN=<your-api-token>
```

## CLI Usage
Common commands for project maintenance:
- `python manage.py init` — initialize storage and default config
- `python manage.py runserver` — launch the development backend
- `python manage.py backup` — export backup data
- `python manage.py restore` — restore from backup

## Important Files
- `manage.py` — application CLI entry point
- `config/sites.yaml` — managed WordPress site definitions
- `frontend/src` — React app source code
- `frontend/src/index.css` — shared frontend styles

## Notes
- Keep `frontend/.env.local` out of version control.
- When modifying frontend styles, use shared CSS classes in `frontend/src/index.css` instead of inline `style={{ ... }}`.
