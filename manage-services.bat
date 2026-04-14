@echo off
setlocal EnableExtensions
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0manage-services.ps1" %*
set "rc=%errorlevel%"
if not "%rc%"=="0" (
  echo.
  echo [ERROR] Service manager exited with code %rc%.
  echo [HINT] Check logs\dev-backend.log and logs\dev-frontend.log.
  pause
)
exit /b %rc%
