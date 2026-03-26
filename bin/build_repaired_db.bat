@echo off
chcp 65001 >nul
setlocal

set ROOT=%~dp0..
pushd "%ROOT%"

echo ========================================
echo 生成修复后的数据库副本（不改当前运行库）
echo ========================================
echo.

python bin\build_repaired_db.py --result-file "2024*_results.xlsx"
set CODE=%ERRORLEVEL%

echo.
if %CODE%==0 (
  echo 已生成修复库，请按提示替换 contracts.db。
) else (
  echo 生成失败，错误码: %CODE%
)

popd
pause
