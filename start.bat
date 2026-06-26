@echo off
chcp 65001 >nul
title Sayit
set "ROOT=%~dp0"
set ELECTRON_RUN_AS_NODE=

echo ── Sayit Launcher ──
echo.

:: ── Step 0: Kill existing Sayit processes ──
:: Kill ALL cmd.exe running npx.cmd electron .
for /f "tokens=2 delims=," %%a in ('wmic process where "name='cmd.exe' and commandline like '%%npx%%electron%%'" get processid /format:csv 2^>nul ^| findstr /v "ProcessId"') do (
    taskkill /F /PID %%a >nul 2>&1
)
:: Kill electron.exe
taskkill /F /IM electron.exe >nul 2>&1
taskkill /F /IM Sayit.exe >nul 2>&1

:: Kill any Python running server.py
for /f "tokens=2 delims=," %%a in ('wmic process where "name='python.exe' and commandline like '%%server.py%%'" get processid /format:csv 2^>nul ^| findstr /v "ProcessId"') do (
    echo [清理] 发现 server.py 进程 PID=%%a，正在终止...
    taskkill /F /PID %%a >nul 2>&1
)

:: Kill port 17890
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":17890" ^| findstr "LISTENING" 2^>nul') do (
    echo [清理] 发现端口 17890 占用，PID=%%a，正在终止...
    taskkill /F /PID %%a >nul 2>&1
)
echo [清理] 端口检查完毕。
echo.

:: ── Step 2: Start Electron (it manages Python backend lifecycle) ──
echo [启动] Electron 界面（Python 后端由 Electron 自动管理）...
cd /d "%ROOT%\frontend"
npx electron .
echo [完毕] Electron 已退出。
pause