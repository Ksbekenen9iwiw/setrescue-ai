@echo off
setlocal
cd /d "%~dp0"
title SetRescue AI - Launch
if not exist "backend\.venv\Scripts\python.exe" (
  echo Python environment missing. Run setup.bat first.
  exit /b 1
)
if not exist "frontend\node_modules" (
  echo Frontend dependencies missing. Run setup.bat first.
  exit /b 1
)
echo Starting SetRescue AI on your laptop...
start "SetRescue - API" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "SetRescue - Web" /D "%~dp0frontend" cmd /k "npm run dev -- --host 127.0.0.1"
echo.
echo Open http://localhost:5173
echo API documentation: http://localhost:8000/docs
echo Keep both terminal windows open while using SetRescue.
exit /b 0
