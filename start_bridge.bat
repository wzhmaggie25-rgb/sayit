@echo off
setlocal enabledelayedexpansion

:: Agent Bridge Launcher
:: Pure ASCII / CRLF batch -- safe for Windows CMD double-click

:: Determine script directory as repo root
set "_ROOT=%~dp0"
if "%_ROOT:~-1%"=="\" set "_ROOT=%_ROOT:~0,-1%"

:: Verify repository structure
if not exist "%_ROOT%\.git" (
    echo ERROR: .git not found at %_ROOT%
    echo This script must run from the SayIt repository root.
    pause
    exit /b 1
)

if not exist "%_ROOT%\tools\agent_bridge\bridge.py" (
    echo ERROR: tools\agent_bridge\bridge.py not found.
    echo Bridge core module is missing.
    pause
    exit /b 1
)

:: Locate Python -- priority order: py -3, python, fallback to 3.12
set "_PYTHON="

where py >nul 2>nul
if not errorlevel 1 (
    py -3 --version >nul 2>nul
    if not errorlevel 1 (
        set "_PYTHON=py -3"
    )
)

if "%_PYTHON%"=="" (
    where python >nul 2>nul
    if not errorlevel 1 (
        python --version >nul 2>nul
        if not errorlevel 1 (
            set "_PYTHON=python"
        )
    )
)

if "%_PYTHON%"=="" (
    if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe" (
        set "_PYTHON=%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
    )
)

if "%_PYTHON%"=="" (
    echo ERROR: Could not find Python. Install Python 3.10+ and try again.
    pause
    exit /b 1
)

echo ========================================
echo  Agent Bridge - Claude Code Task Runner
echo ========================================
echo  Project: %_ROOT%
echo  Python : %_PYTHON%
echo  Ctrl+C to stop safely
echo ========================================
echo.

cd /d "%_ROOT%"

%_PYTHON% tools\agent_bridge\bridge.py %*

set "_EXIT_CODE=%ERRORLEVEL%"
if "%_EXIT_CODE%" neq "0" (
    echo.
    echo Bridge exited with code %_EXIT_CODE%. See logs for details.
    pause
) else (
    echo.
    echo Bridge stopped.
    pause
)

endlocal