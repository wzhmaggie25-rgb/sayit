# Clean restart for Sayit (Typeless architecture: Electron manages Python backend)
Write-Host "=== Killing Sayit processes ==="

# Kill cmd.exe windows running npx electron
Get-CimInstance -ClassName Win32_Process -Filter "Name = 'cmd.exe'" | Where-Object {
    $_.CommandLine -match 'npx.*electron'
} | ForEach-Object {
    Write-Host "Killing cmd PID $($_.ProcessId): $($_.CommandLine.Substring(0, [Math]::Min(80, $_.CommandLine.Length)))"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# Kill electron
Get-Process -Name electron -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Killing electron PID $($_.Id)"
    Stop-Process -Id $_.Id -Force
}

# Kill python server
Get-CimInstance -ClassName Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -match 'server\.py'
} | ForEach-Object {
    Write-Host "Killing python PID $($_.ProcessId): server.py"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# Also kill by port
$portProc = netstat -ano | Select-String ':17890' | Select-String 'LISTENING' | ForEach-Object { $_ -replace '.*\s+(\d+)$', '$1' }
if ($portProc) {
    Write-Host "Killing port 17890 owner PID $portProc"
    Stop-Process -Id $portProc -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 3

Write-Host "=== Starting Electron (manages Python backend) ==="
$electronPath = "D:\code\sayit_zcode\frontend\node_modules\.bin\electron.cmd"
if (-not (Test-Path $electronPath)) {
    # Fallback to npx
    Start-Process -WindowStyle Hidden -FilePath npx.cmd -ArgumentList 'electron', '.' -WorkingDirectory 'D:\code\sayit_zcode\frontend'
} else {
    Start-Process -FilePath $electronPath -ArgumentList '.' -WorkingDirectory 'D:\code\sayit_zcode\frontend'
}

Start-Sleep -Seconds 8

Write-Host "=== Status ==="
netstat -ano | Select-String ':17890'
Write-Host "=== Log tail ==="
$logPath = "$env:APPDATA\Sayit\sayit.log"
if (Test-Path $logPath) {
    Get-Content $logPath -Tail 15
} else {
    Write-Host "(no log file)"
}

Write-Host "=== DONE ==="