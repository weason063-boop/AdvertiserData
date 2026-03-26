@echo off
chcp 65001 >nul
setlocal

set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%day1_restart_and_regression.ps1

if not exist "%PS_SCRIPT%" (
  echo [ERROR] Missing script: %PS_SCRIPT%
  exit /b 1
)

powershell -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
exit /b %errorlevel%

