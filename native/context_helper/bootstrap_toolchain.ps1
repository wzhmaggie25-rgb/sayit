param(
  [switch]$AcceptPackageAgreements
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  throw "winget.exe was not found. Install Visual Studio Build Tools with C++ and CMake manually."
}

$agreementArgs = @()
if ($AcceptPackageAgreements) {
  $agreementArgs = @("--accept-package-agreements", "--accept-source-agreements")
}

Write-Host "Installing CMake..."
winget install --id Kitware.CMake -e --source winget --silent @agreementArgs
if ($LASTEXITCODE -ne 0) {
  throw "CMake installation failed with exit code $LASTEXITCODE."
}

Write-Host "Installing Visual Studio 2022 Build Tools with C++ workload..."
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --source winget `
  --override "--quiet --wait --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.CMake.Project --add Microsoft.VisualStudio.Component.Windows11SDK.22621" `
  @agreementArgs
if ($LASTEXITCODE -ne 0) {
  throw "Visual Studio Build Tools installation failed with exit code $LASTEXITCODE."
}

Write-Host "Toolchain bootstrap requested. Open a new terminal, then run native/context_helper/build.ps1."
