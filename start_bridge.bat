@echo off
chcp 65001 >nul

:: A: Start from the repository root (script parent dir)
cd /d "%~dp0"

:: Verify we're in the SayIt repo
if not exist "tools\agent_bridge\bridge.py" (
    echo ERROR: tools\agent_bridge\bridge.py not found.
    echo Expected to be run from the SayIt project root.
    pause
    exit /b 1
)

if not exist ".git" (
    echo ERROR: Not a Git repository.  Run from the SayIt project root.
    pause
    exit /b 1
)

echo ========================================
echo  Agent Bridge — Claude Code Task Runner
echo ========================================
echo  Project: %cd%
echo  Ctrl+C to stop safely
echo ========================================
echo.

python tools\agent_bridge\bridge.py %*
if errorlevel 1 (
    echo.
    echo Bridge exited with code %errorlevel%
    pause
)