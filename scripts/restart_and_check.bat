@echo off
setlocal EnableExtensions
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_and_check.ps1" %*
set "rc=%errorlevel%"
if not "%rc%"=="0" (
  echo.
  echo [ERROR] restart_and_check.ps1 exited with code %rc%.
  echo [HINT] Try running this as Administrator.
)
exit /b %rc%
