@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "RUNTIME_DIR=%SCRIPT_DIR%.dashboard-runtime"

if "%BACKEND_PORT%"=="" set "BACKEND_PORT=8000"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=5173"

call :kill_from_pid_file "%RUNTIME_DIR%\backend.pid" "backend"
call :kill_from_pid_file "%RUNTIME_DIR%\frontend.pid" "frontend"

call :kill_matching_port %BACKEND_PORT% "uvicorn|app.main" "backend"
call :kill_matching_port %FRONTEND_PORT% "vite|node.*vite" "frontend"

echo Dashboard stop command completed.
exit /b 0

:kill_from_pid_file
set "PID_FILE=%~1"
set "LABEL=%~2"
if exist "%PID_FILE%" (
  set /p PID=<"%PID_FILE%"
  if not "!PID!"=="" (
    echo Stopping %LABEL% PID !PID!
    taskkill /PID !PID! /T /F >nul 2>nul
  )
  del "%PID_FILE%" >nul 2>nul
)
exit /b 0

:kill_matching_port
set "PORT_TO_CHECK=%~1"
set "COMMAND_PATTERN=%~2"
set "LABEL=%~3"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT_TO_CHECK% .*LISTENING"') do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$proc = Get-CimInstance Win32_Process -Filter 'ProcessId=%%P'; if ($proc -and $proc.CommandLine -match '%COMMAND_PATTERN%') { Stop-Process -Id %%P -Force; Write-Output 'Stopped %LABEL% process on port %PORT_TO_CHECK% (PID %%P).' }"
)
exit /b 0
