@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0.."
if not defined GRIT_BACKEND_PORT set "GRIT_BACKEND_PORT=8001"
set "PYTHONPATH=src"

python -m uvicorn grit_day_trading.api:app --host 127.0.0.1 --port %GRIT_BACKEND_PORT%
