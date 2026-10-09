@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SetRescue AI - First-time setup

echo.
echo   SetRescue AI - local Windows setup
echo   -----------------------------------

if not exist "backend\.venv\Scripts\python.exe" (
    echo [1/5] Creating Python virtual environment...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3.12 --version >nul 2>&1
        if not errorlevel 1 (
            py -3.12 -m venv "backend\.venv"
        ) else (
            py -3 -m venv "backend\.venv"
        )
    ) else (
        python -m venv "backend\.venv"
    )
    if errorlevel 1 goto :error
) else (
    echo [1/5] Python environment already exists.
)

echo [2/5] Installing backend dependencies...
"backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 goto :error

if not exist "backend\.env" (
    echo [3/5] Creating local encryption settings...
    "backend\.venv\Scripts\python.exe" -c "from cryptography.fernet import Fernet; print('SETRESCUE_ENCRYPTION_KEY=' + Fernet.generate_key().decode()); print('SETRESCUE_DEMO_EMAIL=true'); print('SETRESCUE_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173')" > "backend\.env"
    if errorlevel 1 goto :error
) else (
    echo [3/5] Preserving existing .env and API credentials.
)

if not exist "backend\data" mkdir "backend\data"
echo [4/5] Preparing SQLite database...
pushd "backend"
".venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 (
    popd
    goto :error
)
popd

echo [5/5] Installing frontend dependencies...
where npm >nul 2>&1
if errorlevel 1 (
    echo Node.js and npm were not found in PATH.
    goto :error
)
pushd "frontend"
call npm install
if errorlevel 1 (
    popd
    goto :error
)
popd

echo.
echo Setup completed. Run start.bat to open the local application.
exit /b 0

:error
echo.
echo Setup did not complete. Check the error above.
echo Required: Node.js 20+ and Python 3.12 recommended, plus internet for first install.
exit /b 1
