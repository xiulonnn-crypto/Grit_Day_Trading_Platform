@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
if not defined GRIT_BACKEND_PORT set "GRIT_BACKEND_PORT=8001"
if not defined GRIT_FRONTEND_PORT set "GRIT_FRONTEND_PORT=5173"
set "BACKEND_URL=http://127.0.0.1:%GRIT_BACKEND_PORT%"
set "FRONTEND_URL=http://127.0.0.1:%GRIT_FRONTEND_PORT%"
if not defined VITE_API_PROXY set "VITE_API_PROXY=%BACKEND_URL%"

pushd "%ROOT%" >nul

if /I "%~1"=="--check" goto check

echo [Grit] Starting local review cockpit...
echo [Grit] Backend:  %BACKEND_URL%
echo [Grit] Frontend: %FRONTEND_URL%
echo.

call :require python
if errorlevel 1 goto failed
call :require npm.cmd
if errorlevel 1 goto failed

call :is_backend_ready
if errorlevel 1 (
  echo [Grit] Backend is not running. Launching...
  start "Grit Day Trading Backend" /min "%ROOT%scripts\run-backend.cmd"
  call :wait_backend
  if errorlevel 1 goto backend_failed
) else (
  echo [Grit] Backend already running.
)

call :is_frontend_ready
if errorlevel 1 (
  echo [Grit] Frontend is not running. Launching...
  start "Grit Day Trading Frontend" /min "%ROOT%scripts\run-frontend.cmd"
  call :wait_frontend
  if errorlevel 1 goto frontend_failed
) else (
  echo [Grit] Frontend already running.
)

echo.
echo [Grit] Ready: %FRONTEND_URL%
if not "%GRIT_NO_BROWSER%"=="1" start "" "%FRONTEND_URL%"
popd >nul
exit /b 0

:check
echo [Grit] Shortcut check
echo [Grit] Root:     %ROOT%
echo [Grit] Backend:  %BACKEND_URL%
echo [Grit] Frontend: %FRONTEND_URL%
call :require python
if errorlevel 1 goto failed
call :require npm.cmd
if errorlevel 1 goto failed
echo [Grit] OK
popd >nul
exit /b 0

:require
where %~1 >nul 2>nul
if errorlevel 1 (
  echo [Grit][ERROR] %~1 was not found in PATH.
  exit /b 1
)
exit /b 0

:is_backend_ready
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri '%BACKEND_URL%/api/healthz' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 }; exit 1 } catch { exit 1 }"
exit /b %ERRORLEVEL%

:is_frontend_ready
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%FRONTEND_URL%/' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 }; exit 1 } catch { exit 1 }"
exit /b %ERRORLEVEL%

:wait_backend
for /L %%I in (1,1,40) do (
  call :is_backend_ready
  if not errorlevel 1 exit /b 0
  timeout /t 1 /nobreak >nul
)
exit /b 1

:wait_frontend
for /L %%I in (1,1,40) do (
  call :is_frontend_ready
  if not errorlevel 1 exit /b 0
  timeout /t 1 /nobreak >nul
)
exit /b 1

:backend_failed
echo [Grit][ERROR] Backend did not become ready on %BACKEND_URL%.
echo [Grit][ERROR] Run scripts\run-backend.cmd to inspect the backend console.
goto failed

:frontend_failed
echo [Grit][ERROR] Frontend did not become ready on %FRONTEND_URL%.
echo [Grit][ERROR] Run scripts\run-frontend.cmd to inspect the frontend console.
goto failed

:failed
echo.
if /I "%~1"=="--check" (
  echo [Grit] Startup failed.
  popd >nul
  exit /b 1
)
if "%GRIT_NO_PAUSE%"=="1" (
  echo [Grit] Startup failed.
  popd >nul
  exit /b 1
)
echo [Grit] Startup failed. Press any key to close this window.
pause >nul
popd >nul
exit /b 1
