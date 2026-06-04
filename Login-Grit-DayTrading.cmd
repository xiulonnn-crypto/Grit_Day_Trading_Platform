@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
if defined VITE_API_PROXY (set "VITE_API_PROXY_USER_SET=1") else set "VITE_API_PROXY_USER_SET=0"
if not defined GRIT_BACKEND_PORT set "GRIT_BACKEND_PORT=8001"
if not defined GRIT_FRONTEND_PORT set "GRIT_FRONTEND_PORT=5173"
if not defined GRIT_BACKEND_FALLBACK_START set "GRIT_BACKEND_FALLBACK_START=8011"
if not defined GRIT_FRONTEND_FALLBACK_START set "GRIT_FRONTEND_FALLBACK_START=5183"
set "REQUESTED_BACKEND_PORT=%GRIT_BACKEND_PORT%"
set "REQUESTED_FRONTEND_PORT=%GRIT_FRONTEND_PORT%"
set "USING_FALLBACK_PORTS=0"
call :update_urls
set "REQUIRED_BACKEND_ROUTE=/api/strategy-test-runs"
set "REQUIRED_REVIEW_ROUTE=/api/review/summary"
set "REQUIRED_STRATEGY_TEMPLATE=momentum_mean_reversion_v1"

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
if not errorlevel 1 goto backend_ready
call :is_backend_running
if errorlevel 1 goto backend_launch
echo [Grit] Backend on %BACKEND_URL% is stale. Choosing fallback ports...
call :activate_fallback_ports
if errorlevel 1 goto fallback_failed
goto backend_launch
:backend_ready
echo [Grit] Backend already running.
goto backend_done
:backend_launch
echo [Grit] Launching backend on %BACKEND_URL%...
start "Grit Day Trading Backend %GRIT_BACKEND_PORT%" /min "%ROOT%scripts\run-backend.cmd"
call :wait_backend
if errorlevel 1 goto backend_failed
:backend_done
call :is_backend_review_ready
if errorlevel 1 goto backend_runtime_failed

call :is_frontend_ready
if not errorlevel 1 goto frontend_ready
echo [Grit] Launching frontend on %FRONTEND_URL%...
start "Grit Day Trading Frontend %GRIT_FRONTEND_PORT%" /min "%ROOT%scripts\run-frontend.cmd"
call :wait_frontend
if errorlevel 1 goto frontend_failed
goto frontend_done
:frontend_ready
echo [Grit] Frontend already running.
:frontend_done

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
call :is_backend_running
if errorlevel 1 goto backend_not_running_check
call :is_backend_ready
if errorlevel 1 goto backend_incompatible
echo [Grit] Backend route check OK.
goto backend_checked
:backend_not_running_check
echo [Grit][ERROR] Backend is not running on %BACKEND_URL%.
echo [Grit][ERROR] Run Login-Grit-DayTrading.cmd to start the local cockpit, then run --check again.
goto failed
:backend_checked
call :is_frontend_ready
if errorlevel 1 (
  echo [Grit][ERROR] Frontend is not responding on %FRONTEND_URL%.
  echo [Grit][ERROR] Run Login-Grit-DayTrading.cmd to start the local cockpit, then run --check again.
  goto failed
)
echo [Grit] Frontend check OK.
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

:update_urls
set "BACKEND_URL=http://127.0.0.1:%GRIT_BACKEND_PORT%"
set "FRONTEND_URL=http://127.0.0.1:%GRIT_FRONTEND_PORT%"
if "%VITE_API_PROXY_USER_SET%"=="0" set "VITE_API_PROXY=%BACKEND_URL%"
exit /b 0

:activate_fallback_ports
call :choose_backend_fallback_port
if errorlevel 1 exit /b 1
call :choose_frontend_fallback_port
if errorlevel 1 exit /b 1
set "USING_FALLBACK_PORTS=1"
call :update_urls
echo [Grit] Fallback backend:  %BACKEND_URL%
echo [Grit] Fallback frontend: %FRONTEND_URL%
if "%VITE_API_PROXY_USER_SET%"=="1" (
  echo [Grit][WARN] VITE_API_PROXY is user-defined as %VITE_API_PROXY%.
)
exit /b 0

:choose_backend_fallback_port
set "SELECTED_PORT="
for /f %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$start=[int]$env:GRIT_BACKEND_FALLBACK_START; for ($p=$start; $p -lt $start + 50; $p++) { try { $tcp=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $p); $tcp.Start(); $tcp.Stop(); Write-Output $p; exit 0 } catch {} }; exit 1"') do set "SELECTED_PORT=%%P"
if not defined SELECTED_PORT exit /b 1
set "GRIT_BACKEND_PORT=%SELECTED_PORT%"
exit /b 0

:choose_frontend_fallback_port
set "SELECTED_PORT="
for /f %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$start=[int]$env:GRIT_FRONTEND_FALLBACK_START; for ($p=$start; $p -lt $start + 50; $p++) { try { $tcp=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $p); $tcp.Start(); $tcp.Stop(); Write-Output $p; exit 0 } catch {} }; exit 1"') do set "SELECTED_PORT=%%P"
if not defined SELECTED_PORT exit /b 1
set "GRIT_FRONTEND_PORT=%SELECTED_PORT%"
exit /b 0

:is_backend_ready
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $h = Invoke-RestMethod -Uri '%BACKEND_URL%/api/healthz' -TimeoutSec 2; if ($h.status -ne 'ok') { exit 1 }; $o = Invoke-RestMethod -Uri '%BACKEND_URL%/openapi.json' -TimeoutSec 2; $paths = $o.paths.PSObject.Properties.Name; if (-not ($paths -contains '%REQUIRED_BACKEND_ROUTE%')) { exit 1 }; if (-not ($paths -contains '%REQUIRED_REVIEW_ROUTE%')) { exit 1 }; $t = Invoke-RestMethod -Uri '%BACKEND_URL%/api/strategy-templates' -TimeoutSec 2; if (($t.items | ForEach-Object { $_.template_key }) -contains '%REQUIRED_STRATEGY_TEMPLATE%') { exit 0 }; exit 1 } catch { exit 1 }"
exit /b %ERRORLEVEL%

:is_backend_running
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri '%BACKEND_URL%/api/healthz' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 }; exit 1 } catch { exit 1 }"
exit /b %ERRORLEVEL%

:is_frontend_ready
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%FRONTEND_URL%/' -TimeoutSec 2; if ($r.StatusCode -ne 200) { exit 1 }; $h = Invoke-RestMethod -Uri '%FRONTEND_URL%/api/healthz' -TimeoutSec 2; if ($h.status -eq 'ok') { exit 0 }; exit 1 } catch { exit 1 }"
exit /b %ERRORLEVEL%

:is_backend_review_ready
curl.exe -fsS --max-time 15 "%BACKEND_URL%%REQUIRED_REVIEW_ROUTE%" -o NUL >nul 2>nul
exit /b %ERRORLEVEL%

:print_port_owner
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /C:":%~1 " ^| findstr /C:"LISTENING"') do echo [Grit] Port %~1 owner PID: %%P
exit /b 0

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
call :print_port_owner %GRIT_BACKEND_PORT%
goto failed

:backend_runtime_failed
echo [Grit][ERROR] Backend is listening on %BACKEND_URL%, but the review API is not usable.
echo [Grit][ERROR] The data DB may be locked by another backend process, or the review route is returning 500.
call :print_port_owner %GRIT_BACKEND_PORT%
if "%USING_FALLBACK_PORTS%"=="1" (
  echo [Grit][ERROR] The original backend port may still be holding the same DB:
  call :print_port_owner %REQUESTED_BACKEND_PORT%
)
echo [Grit][ERROR] Close the stale backend process shown above, then run Login-Grit-DayTrading.cmd again.
goto failed

:fallback_failed
echo [Grit][ERROR] Default backend is stale, and no fallback backend/frontend port could be selected.
echo [Grit][ERROR] Set GRIT_BACKEND_PORT and GRIT_FRONTEND_PORT to free ports, then run Login-Grit-DayTrading.cmd again.
goto failed

:backend_incompatible
echo [Grit][ERROR] Backend is responding on %BACKEND_URL% but is missing required route %REQUIRED_BACKEND_ROUTE% / %REQUIRED_REVIEW_ROUTE% or strategy template %REQUIRED_STRATEGY_TEMPLATE%.
echo [Grit][ERROR] A stale backend process is likely occupying port %GRIT_BACKEND_PORT%.
call :print_port_owner %GRIT_BACKEND_PORT%
echo [Grit][ERROR] Run Login-Grit-DayTrading.cmd without --check to auto-start on fallback ports, or close the old process and retry.
echo [Grit][ERROR] For a read-only check, run Login-Grit-DayTrading.cmd --check after restarting.
goto failed

:frontend_failed
echo [Grit][ERROR] Frontend did not become ready on %FRONTEND_URL%.
echo [Grit][ERROR] Run scripts\run-frontend.cmd to inspect the frontend console.
call :print_port_owner %GRIT_FRONTEND_PORT%
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
