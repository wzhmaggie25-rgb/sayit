@echo off
setlocal enabledelayedexpansion

echo Installing SayIt Bridge desktop shortcut...
echo.

:: Locate PowerShell
where powershell >nul 2>nul
if errorlevel 1 (
    echo ERROR: PowerShell not found. Cannot create shortcut.
    pause
    exit /b 1
)

:: Determine script directory (repo root)
set "_ROOT=%~dp0"
if "%_ROOT:~-1%"=="\" set "_ROOT=%_ROOT:~0,-1%"

echo Repository root: %_ROOT%
echo.

powershell -ExecutionPolicy Bypass -File "%_ROOT%\tools\agent_bridge\install_shortcut.ps1" -RepoRoot "%_ROOT%"

if errorlevel 1 (
    echo ERROR: Shortcut installation failed.
    pause
    exit /b 1
)

echo.
echo Shortcut created successfully!
echo Look for "SayIt AI Bridge" on your desktop.
echo.
pause
exit /b 0
endlocal