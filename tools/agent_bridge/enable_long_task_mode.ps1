$ErrorActionPreference = 'Stop'

$bridgeDir = $PSScriptRoot
$configPath = Join-Path $bridgeDir 'bridge_config.json'
$lockPath = Join-Path $bridgeDir 'bridge.lock'
$logPath = Join-Path $bridgeDir 'bridge.log'
$statePath = Join-Path $bridgeDir 'bridge_state.json'

if (Test-Path $lockPath) {
    $rawPid = (Get-Content $lockPath -Raw -ErrorAction SilentlyContinue).Trim()
    if ($rawPid -match '^\d+$') {
        $running = Get-Process -Id ([int]$rawPid) -ErrorAction SilentlyContinue
        if ($null -ne $running) {
            throw "SayIt AI Bridge is already running (PID $rawPid). Stop it before changing long-task settings."
        }
    }
    Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
}

$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($null -eq $claude) {
    throw 'Claude Code was not found on PATH. Run `claude --version` in a terminal and fix PATH first.'
}

$config = [ordered]@{
    branch = 'feature/silent-learning-stabilization'
    remote = 'origin'
    poll_interval_seconds = 30
    claude_timeout_seconds = 10800
    claude_binary = 'claude'
    log_level = 'info'
    log_file = $logPath
    lock_file = $lockPath
    state_file = $statePath
    claude_allowed_tools = @(
        'Read'
        'Edit'
        'Write'
        'Bash(git*)'
        'Bash(python*)'
        'Bash(pytest*)'
        'Bash(node*)'
        'Bash(npm*)'
        'Bash(npx*)'
        'Bash(powershell*)'
        'Bash(claude*)'
    )
}

$config | ConvertTo-Json -Depth 5 | Set-Content -Path $configPath -Encoding UTF8

Write-Host ''
Write-Host 'SayIt Bridge long-task mode enabled.' -ForegroundColor Green
Write-Host "Config: $configPath"
Write-Host 'Claude timeout: 10800 seconds (3 hours)'
Write-Host 'Additional tools: node, npm, npx, PowerShell'
Write-Host ''
Write-Host 'Next: start the desktop shortcut `SayIt AI Bridge`.' -ForegroundColor Cyan
