@echo off
chcp 65001 >nul
set "ROOT=%~dp0"
set "FRONTEND=%ROOT%\frontend"
set ELECTRON_RUN_AS_NODE=

:: ── Step 0: Kill existing Sayit processes ──
:: Kill ALL cmd.exe windows that are running npx.cmd electron .
for /f "tokens=2 delims=," %%a in ('wmic process where "name='cmd.exe' and commandline like '%%npx%%electron%%'" get processid /format:csv 2^>nul ^| findstr /v "ProcessId"') do (
    taskkill /F /PID %%a >nul 2>&1
)
:: Kill electron.exe processes
taskkill /F /IM electron.exe >nul 2>&1
:: Kill any Python running server.py
for /f "tokens=2 delims=," %%a in ('wmic process where "name='python.exe' and commandline like '%%server.py%%'" get processid /format:csv 2^>nul ^| findstr /v "ProcessId"') do (
    taskkill /F /PID %%a >nul 2>&1
)
:: Kill port 17890
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":17890" ^| findstr "LISTENING" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Wait for cleanup
timeout /t 2 /nobreak >nul

:: ── Start Electron (it manages Python backend lifecycle) ──
cd /d "%FRONTEND%"
start "Sayit" npx.cmd electron .