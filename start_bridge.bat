@echo off
setlocal

cd /d "%~dp0"

if not exist ".git" goto bad_repo
if not exist "tools\agent_bridge\bridge.py" goto bad_bridge

echo ========================================
echo Agent Bridge - Claude Code Task Runner
echo ========================================
echo Project: %CD%
echo Press Ctrl+C to stop
echo ========================================
echo.

python "tools\agent_bridge\bridge.py" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Bridge exited with code %EXIT_CODE%
    pause
)

exit /b %EXIT_CODE%

:bad_repo
echo ERROR: .git directory not found.
echo Put this file in the SayIt repository root.
pause
exit /b 1

:bad_bridge
echo ERROR: tools\agent_bridge\bridge.py not found.
echo Run git pull --ff-only and try again.
pause
exit /b 1
