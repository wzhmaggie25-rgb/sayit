param(
  [string]$Exe = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Exe) {
  $candidates = @(
    (Join-Path $Root "build\Release\sayit_context_helper.exe"),
    (Join-Path $Root "build\Debug\sayit_context_helper.exe"),
    (Join-Path $Root "build\sayit_context_helper.exe")
  )
  $Exe = ($candidates | Where-Object { Test-Path $_ } | Select-Object -First 1)
}
if (-not $Exe -or -not (Test-Path $Exe)) {
  throw "sayit_context_helper.exe was not found. Run native/context_helper/build.ps1 first."
}

$request = '{"id":"probe","method":"get_full_context","params":{}}'
$response = $request | & $Exe
if (-not $response) {
  throw "Context helper returned no response."
}
$json = $response | ConvertFrom-Json
if (-not $json.ok) {
  throw "Context helper returned error: $response"
}

$json.result | ConvertTo-Json -Depth 8
