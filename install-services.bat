@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Billing Service Installer

set "NSSM=C:\Users\norah\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
set "ASCII_PROJECT_DIR=C:\AGM_BILLING"
set "ASCII_DIR_OK=0"

for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
for %%I in ("%PROJECT_DIR%\..") do set "REPO_DIR=%%~fI"
if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"
set "PYTHON=%REPO_DIR%\.venv\Scripts\python.exe"

echo [INFO] Checking admin permission...
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo [ERROR] Please run this script as Administrator.
  pause
  exit /b 1
)

if not exist "%NSSM%" (
  echo [ERROR] nssm.exe not found: %NSSM%
  pause
  exit /b 1
)
if not exist "%PYTHON%" (
  echo [ERROR] Python not found: %PYTHON%
  pause
  exit /b 1
)
if not exist "%PROJECT_DIR%\scripts\serve_frontend.py" (
  echo [ERROR] Frontend server script not found: %PROJECT_DIR%\scripts\serve_frontend.py
  pause
  exit /b 1
)

call :path_exists "%ASCII_PROJECT_DIR%" ASCII_DIR_OK
if not "%ASCII_DIR_OK%"=="1" (
  mklink /J "%ASCII_PROJECT_DIR%" "%PROJECT_DIR%" >nul 2>&1
)
call :path_exists "%ASCII_PROJECT_DIR%" ASCII_DIR_OK
if "%ASCII_DIR_OK%"=="1" (
  set "SERVICE_PROJECT_DIR=%ASCII_PROJECT_DIR%"
) else (
  set "SERVICE_PROJECT_DIR=%PROJECT_DIR%"
)
set "LOG_DIR=%SERVICE_PROJECT_DIR%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
if not exist "%SERVICE_PROJECT_DIR%\web\dist\index.html" (
  echo [ERROR] Frontend build output not found: %SERVICE_PROJECT_DIR%\web\dist\index.html
  pause
  exit /b 1
)

echo --- Sync billing-backend service ---
sc.exe query billing-backend >nul 2>&1
if errorlevel 1 (
  "%NSSM%" install billing-backend "%PYTHON%" "-m uvicorn api.main:app --host 0.0.0.0 --port 8000"
)
"%NSSM%" set billing-backend Application "%PYTHON%"
"%NSSM%" set billing-backend AppParameters "-m uvicorn api.main:app --host 0.0.0.0 --port 8000"
"%NSSM%" set billing-backend AppDirectory "%SERVICE_PROJECT_DIR%"
"%NSSM%" set billing-backend AppStdout "%LOG_DIR%\backend.log"
"%NSSM%" set billing-backend AppStderr "%LOG_DIR%\backend.log"

echo --- Sync billing-frontend service ---
sc.exe query billing-frontend >nul 2>&1
if errorlevel 1 (
  "%NSSM%" install billing-frontend "%PYTHON%" "scripts\serve_frontend.py --host 0.0.0.0 --port 5173 --dir web\dist"
)
"%NSSM%" set billing-frontend Application "%PYTHON%"
"%NSSM%" set billing-frontend AppParameters "scripts\serve_frontend.py --host 0.0.0.0 --port 5173 --dir web\dist"
"%NSSM%" set billing-frontend AppDirectory "%SERVICE_PROJECT_DIR%"
"%NSSM%" set billing-frontend AppStdout "%LOG_DIR%\frontend.log"
"%NSSM%" set billing-frontend AppStderr "%LOG_DIR%\frontend.log"

echo --- Restart services ---
"%NSSM%" stop billing-backend >nul 2>&1
"%NSSM%" stop billing-frontend >nul 2>&1
timeout /t 2 /nobreak >nul
"%NSSM%" start billing-backend
"%NSSM%" start billing-frontend

echo.
echo [OK] Services synced and restarted.
echo [INFO] Service project path: %SERVICE_PROJECT_DIR%
echo [INFO] Logs:
echo   - %LOG_DIR%\backend.log
echo   - %LOG_DIR%\frontend.log
pause
exit /b 0

:path_exists
set "%~2=0"
if exist "%~1" (
  set "%~2=1"
  exit /b 0
)
for /f %%R in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path -LiteralPath ''%~1'') { Write-Output 1 } else { Write-Output 0 }"') do set "%~2=%%R"
exit /b 0
