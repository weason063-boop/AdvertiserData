@echo off
chcp 65001 >nul
setlocal

set ROOT=%~dp0..
pushd "%ROOT%"

echo ========================================
echo 修复看板月份数据（清理脏月份 + 重导 2024）
echo ========================================
echo.

python bin\repair_dashboard_months.py --file "2024*.xlsx"
set CODE=%ERRORLEVEL%

echo.
if %CODE%==0 (
  echo 修复完成。
) else (
  echo 修复失败，错误码: %CODE%
)

popd
pause
