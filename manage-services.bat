@echo off
setlocal EnableExtensions
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0manage-services.ps1"
set "rc=%errorlevel%"
if not "%rc%"=="0" (
  echo.
  echo [ERROR] Service manager exited with code %rc%.
  echo [HINT] Please run this script as Administrator.
  pause
)
exit /b %rc%
