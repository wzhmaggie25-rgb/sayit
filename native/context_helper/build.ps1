param(
  [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildDir = Join-Path $Root "build"
$OutDir = Join-Path $BuildDir $Configuration
$Exe = Join-Path $OutDir "sayit_context_helper.exe"
$VcVars = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

if (Test-Path $VcVars) {
  New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
  $Source = Join-Path $Root "src\main.cpp"
  $Obj = Join-Path $OutDir "main.obj"
  $cmd = "call `"$VcVars`" && cl /nologo /std:c++17 /EHsc /W4 /DUNICODE /D_UNICODE /DNOMINMAX /Fo:`"$Obj`" /Fe:`"$Exe`" `"$Source`" user32.lib ole32.lib oleaut32.lib oleacc.lib uiautomationcore.lib psapi.lib"
  cmd /c $cmd
  if ($LASTEXITCODE -ne 0) {
    throw "MSVC direct build failed with exit code $LASTEXITCODE."
  }
  if (-not (Test-Path $Exe)) {
    throw "MSVC direct build completed but sayit_context_helper.exe was not found."
  }
  Write-Host "Built $Exe"
  exit 0
}

$CMake = "cmake"
$knownCMake = "C:\Program Files\CMake\bin\cmake.exe"
if (-not (Get-Command $CMake -ErrorAction SilentlyContinue)) {
  if (Test-Path $knownCMake) {
    $CMake = $knownCMake
  } else {
    throw "cmake.exe was not found in PATH. Install Visual Studio Build Tools with C++ CMake tools, or add CMake to PATH."
  }
}

& $CMake -S $Root -B $BuildDir -A x64
& $CMake --build $BuildDir --config $Configuration

if (-not (Test-Path $Exe)) {
  $Exe = Join-Path $BuildDir "sayit_context_helper.exe"
}
if (-not (Test-Path $Exe)) {
  throw "Build completed but sayit_context_helper.exe was not found."
}

Write-Host "Built $Exe"
