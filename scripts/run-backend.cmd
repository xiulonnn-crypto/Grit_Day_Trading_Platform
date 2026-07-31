@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0.."
if not defined GRIT_BACKEND_PORT set "GRIT_BACKEND_PORT=8001"
set "PYTHONPATH=src"

set "GRIT_BACKEND_PYTHON="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0resolve-backend-python.ps1"`) do if not defined GRIT_BACKEND_PYTHON set "GRIT_BACKEND_PYTHON=%%P"
if not defined GRIT_BACKEND_PYTHON (
  echo [Grit][ERROR] Backend Python requires fastapi, uvicorn, and futu-api.
  echo [Grit][ERROR] Install project dependencies or set GRIT_PYTHON to a compatible python.exe.
  exit /b 1
)

"%GRIT_BACKEND_PYTHON%" -m uvicorn grit_day_trading.api:app --host 127.0.0.1 --port %GRIT_BACKEND_PORT%
