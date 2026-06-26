@echo off
chcp 65001 >nul
title Sayit

echo ── Sayit Clean Start ──
echo.

:: ── Step 0: Kill ALL existing Sayit backend + Electron ──
echo [清理] 杀掉所有 Sayit 相关进程...
for /f "tokens=2 delims=," %%a in ('wmic process where "name='python.exe' and commandline like '%%server.py%%'" get processid /format:csv 2^>nul ^| findstr /v "ProcessId"') do (
    echo [清理] 发现 server.py PID=%%a，终止...
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=2 delims=," %%a in ('wmic process where "name='cmd.exe' and commandline like '%%npx%%electron%%'" get processid /format:csv 2^>nul ^| findstr /v "ProcessId"') do (
    taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /IM electron.exe >nul 2>&1
taskkill /F /IM Sayit.exe >nul 2>&1

:: Wait for cleanup
timeout /t 2 /nobreak >nul

:: ── Step 1: Start Python backend ──
echo [启动] Python 后端...
cd /d "%~dp0"
start "Sayit-Backend" python server.py

:: Wait for backend to be ready
echo [等待] 等待后端就绪...
:wait_loop
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":17890" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 goto wait_loop
echo [就绪] 后端已启动 (端口 17890)

:: ── Step 2: Start Electron (SAYIT_SKIP_BACKEND=1 to prevent duplicate backend) ──
echo [启动] Electron 界面...
cd /d "%~dp0\frontend"
set SAYIT_SKIP_BACKEND=1
start "Sayit" npx.cmd electron .
echo [完成] Sayit 已启动！
echo.
echo 提示：关闭 Sayit 窗口后，请在此窗口按 Ctrl+C 停止后端。
pause