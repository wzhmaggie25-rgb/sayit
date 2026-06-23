@echo off
chcp 65001 >nul
title Sayit
set "ROOT=%~dp0"
set ELECTRON_RUN_AS_NODE=

echo ── Sayit Launcher ──
echo.

:: ── Step 1: Kill any process on port 17890 ──
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":17890" ^| findstr "LISTENING" 2^>nul') do (
    echo [清理] 发现端口 17890 占用，PID=%%a，正在终止...
    taskkill /F /PID %%a >nul 2>&1
)
echo [清理] 端口检查完毕。
echo.

:: ── Step 2: Start Python backend in new window ──
echo [后端] 启动 Python 后端...
cd /d "%ROOT%"
start "Sayit Backend" python server.py
echo.

:: ── Step 3: Wait ──
echo [等待] 等待后端就绪（3 秒）...
ping -n 4 127.0.0.1 >nul
echo.

:: ── Step 4: Start Electron frontend ──
echo [前端] 启动 Electron 界面...
cd /d "%ROOT%\frontend"
npx electron .
echo [前端] Electron 已退出。
pause