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

echo Building frontend assets...
pushd frontend
call npm run build
popd

python manage.py runserver --no-debug