param(
    [string]$RepoRoot = ""
)

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepoRoot = Split-Path -Parent $RepoRoot  # go up from tools\agent_bridge
}

$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "SayIt AI Bridge.lnk"

$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)

$Shortcut.TargetPath = "cmd.exe"
$Shortcut.Arguments = "/k ""$RepoRoot\start_bridge.bat"""
$Shortcut.WorkingDirectory = $RepoRoot
$Shortcut.Description = "SayIt Agent Bridge - Claude Code Task Runner"
$Shortcut.WindowStyle = 1  # Normal window

$Shortcut.Save()

Write-Host "Shortcut created at: $ShortcutPath"
Write-Host "  Target: cmd.exe /k start_bridge.bat"
Write-Host "  Working Dir: $RepoRoot"