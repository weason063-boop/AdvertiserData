@echo off
chcp 65001 >nul
title Antigravity Manager

:: 等待网络和系统准备好
timeout /t 5 /nobreak >nul

:: 使用当前脚本所在目录
set BACKEND_DIR=%~dp0
set FRONTEND_DIR=%~dp0web
set PYTHON=%~dp0..\.venv\Scripts\python.exe

echo ========================================
echo   Antigravity Manager 计费系统启动
echo ========================================
echo.

:: 启动后端
echo [1/2] 启动后端服务...
pushd "%BACKEND_DIR%"
start "Backend" %PYTHON% -m uvicorn api.main:app --host 0.0.0.0 --port 8000
popd

timeout /t 3 /nobreak >nul

:: 启动前端
echo [2/2] 启动前端服务...
pushd "%FRONTEND_DIR%"
start "Frontend" cmd /k npm run dev -- --host 0.0.0.0
popd

timeout /t 4 /nobreak >nul

:: 打开浏览器
start http://localhost:5173

:: 获取本机IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set LOCAL_IP=%%a
)
set LOCAL_IP=%LOCAL_IP: =%

echo.
echo ========================================
echo   所有服务已启动!
echo   本机: http://localhost:5173
echo   局域网: http://%LOCAL_IP%:5173
echo ========================================
echo.
echo 关闭此窗口不影响服务。
pause
