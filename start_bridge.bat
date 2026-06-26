@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ========================================
echo  Agent Bridge — Claude Code Task Runner
echo ========================================
echo  Project: %cd%
echo  Ctrl+C to stop safely
echo ========================================
echo.
python tools/agent_bridge/bridge.py %*
if errorlevel 1 (
    echo.
    echo Bridge exited with code %errorlevel%
    pause
)