@echo off
chcp 65001 >nul
set "ROOT=D:\Soft\code\sayiy1.1\sayit_cg"
set "FRONTEND=%ROOT%\frontend"
set ELECTRON_RUN_AS_NODE=

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":17890" ^| findstr "LISTENING" 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

cd /d "%ROOT%"
start "Sayit Backend" /min python server.py

ping -n 4 127.0.0.1 >nul

cd /d "%FRONTEND%"
set SAYIT_SKIP_BACKEND=1
start "Sayit" npx.cmd electron .
