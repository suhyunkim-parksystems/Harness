@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%backend"
set "FRONTEND_DIR=%SCRIPT_DIR%frontend"
set "RUNTIME_DIR=%SCRIPT_DIR%.dashboard-runtime"

if "%BACKEND_PORT%"=="" set "BACKEND_PORT=8000"
if "%FRONTEND_PORT%"=="" set "FRONTEND_PORT=5173"

if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"

call :require_command python "Python is required to start the FastAPI backend."
if errorlevel 1 exit /b 1
call :require_command node "Node.js is required to start the React frontend."
if errorlevel 1 exit /b 1
call :require_command npm "npm is required to install and run the React frontend."
if errorlevel 1 exit /b 1

call :assert_port_free %BACKEND_PORT% "backend"
if errorlevel 1 exit /b 1
call :assert_port_free %FRONTEND_PORT% "frontend"
if errorlevel 1 exit /b 1

if not exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  echo Creating backend virtual environment...
  python -m venv "%BACKEND_DIR%\.venv"
  if errorlevel 1 exit /b 1
)

echo Installing backend dependencies...
"%BACKEND_DIR%\.venv\Scripts\python.exe" -m pip install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 exit /b 1

if not exist "%FRONTEND_DIR%\node_modules" (
  echo Installing frontend dependencies...
  pushd "%FRONTEND_DIR%"
  call npm install
  set "NPM_STATUS=!errorlevel!"
  popd
  if not "!NPM_STATUS!"=="0" exit /b 1
)

echo Starting backend on http://127.0.0.1:%BACKEND_PORT%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath '%BACKEND_DIR%\.venv\Scripts\python.exe' -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','%BACKEND_PORT%') -WorkingDirectory '%BACKEND_DIR%' -WindowStyle Hidden -PassThru -RedirectStandardOutput '%RUNTIME_DIR%\backend.log' -RedirectStandardError '%RUNTIME_DIR%\backend.err'; Set-Content -Path '%RUNTIME_DIR%\backend.pid' -Value $p.Id"
if errorlevel 1 exit /b 1

echo Starting frontend on http://127.0.0.1:%FRONTEND_PORT%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath 'npm.cmd' -ArgumentList @('run','dev','--','--host','127.0.0.1','--port','%FRONTEND_PORT%') -WorkingDirectory '%FRONTEND_DIR%' -WindowStyle Hidden -PassThru -RedirectStandardOutput '%RUNTIME_DIR%\frontend.log' -RedirectStandardError '%RUNTIME_DIR%\frontend.err'; Set-Content -Path '%RUNTIME_DIR%\frontend.pid' -Value $p.Id"
if errorlevel 1 exit /b 1

echo Dashboard started.
echo Backend:  http://127.0.0.1:%BACKEND_PORT%
echo Frontend: http://127.0.0.1:%FRONTEND_PORT%
echo Logs:     %RUNTIME_DIR%
exit /b 0

:require_command
where %~1 >nul 2>nul
if errorlevel 1 (
  echo %~2
  exit /b 1
)
exit /b 0

:assert_port_free
set "PORT_TO_CHECK=%~1"
set "PORT_LABEL=%~2"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT_TO_CHECK% .*LISTENING"') do (
  echo Port %PORT_TO_CHECK% for %PORT_LABEL% is already in use by PID %%P.
  echo Run stop-dashboard.bat or set a different %PORT_LABEL% port.
  exit /b 1
)
exit /b 0
