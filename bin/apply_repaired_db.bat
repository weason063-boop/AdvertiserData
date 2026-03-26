@echo off
chcp 65001 >nul
setlocal

set ROOT=%~dp0..
pushd "%ROOT%"

set LATEST=
for /f "delims=" %%i in ('dir /b /a:-d /o-d contracts.repaired.*.db 2^>nul') do (
  if not defined LATEST set LATEST=%%i
)

if not defined LATEST (
  echo No repaired DB found. Run bin\build_repaired_db.bat first.
  popd
  pause
  exit /b 1
)

set TS=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TS=%TS: =0%

echo Using repaired DB: %LATEST%
copy /Y contracts.db contracts.before_replace.%TS%.db >nul
if errorlevel 1 (
  echo Backup failed.
  popd
  pause
  exit /b 1
)

copy /Y "%LATEST%" contracts.db >nul
if errorlevel 1 (
  echo Replace failed. Please stop backend service and retry.
  popd
  pause
  exit /b 1
)

echo Replace done. Backup file: contracts.before_replace.%TS%.db
echo Restart backend service then refresh page.

popd
pause
