@echo off

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

if not exist static\index.html (
    echo Building frontend assets...
    pushd frontend
    call npm run build
    popd
)

echo Starting standalone Production Health dashboard on port 63016...
echo This is independent of run.bat/run_dev.bat and stays responsive even
echo while the main app is busy running an update or health check.
python manage.py health-dashboard --no-debug
