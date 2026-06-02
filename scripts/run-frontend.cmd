@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0.."
if not defined GRIT_BACKEND_PORT set "GRIT_BACKEND_PORT=8001"
if not defined GRIT_FRONTEND_PORT set "GRIT_FRONTEND_PORT=5173"
if not defined VITE_API_PROXY set "VITE_API_PROXY=http://127.0.0.1:%GRIT_BACKEND_PORT%"

npm.cmd --prefix web run dev -- --host 127.0.0.1 --port %GRIT_FRONTEND_PORT% --strictPort
