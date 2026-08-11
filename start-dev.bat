@echo off
setlocal enabledelayedexpansion

echo Checking Python dependencies...
python -c "import flask, dotenv, paramiko, yaml, cryptography, requests" 2>NUL
if %errorlevel% neq 0 (
    echo Missing dependencies detected. Installing...
    pip install flask python-dotenv paramiko pyyaml cryptography requests
)

if not exist config\.env (
    echo Initializing workspace configurations...
    python manage.py init
)

if not exist frontend\.env.local (
    if exist config\.env (
        echo Creating frontend\.env.local from config\.env...
        python -c "import pathlib; from dotenv import dotenv_values; env_path=pathlib.Path('config/.env'); out_path=pathlib.Path('frontend/.env.local');\nif env_path.exists(): values=dotenv_values(env_path); token=values.get('API_TOKEN');\nif token: out_path.write_text(f'VITE_API_TOKEN={token}\n', encoding='utf-8'); print('Created frontend/.env.local')"
    ) else (
        echo Warning: config\.env not found; frontend\.env.local cannot be generated automatically.
    )
)

pushd frontend
if not exist node_modules (
    echo Installing frontend dependencies...
    call npm install
)
popd

echo.
echo Launching development servers...
echo.

:: Start the Flask backend server in debug mode on a fixed port
start "WP Site Manager Backend" cmd /k "python manage.py runserver --port 5000"

:: Start the Vite frontend development server on a fixed port
pushd frontend
start "WP Site Manager Frontend" cmd /k "npm run dev"
popd

echo =========================================================================
echo Development environment started successfully!
echo.
echo - Flask Backend (API): http://127.0.0.1:5000 (debug/auto-reload active)
echo - Frontend App (Vite): http://localhost:5173 (hot updates active)
echo.
echo Frontend requests to /api are proxied to port 5000 automatically.
echo Keep the launched terminal windows open. Close them to stop servers.
echo =========================================================================
echo.
pause
