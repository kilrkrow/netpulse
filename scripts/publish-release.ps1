#requires -Version 5.1
<#
.SYNOPSIS
  Build NetPulse, zip the PyInstaller folder, and print SHA256.

.DESCRIPTION
  Wraps build.bat / NetPulse.spec. The spec COLLECT output is a folder named
  NetPulse (NetPulse.exe plus dependencies). This script zips that folder as
  NetPulse-win-x64-v<version>.zip and prints the SHA256 for Chocolatey.

  After a new GitHub release, paste the printed hash into
  pack/chocolatey/netpulse/tools/chocolateyinstall.ps1 and VERIFICATION.txt.

.PARAMETER Version
  Release version without a leading v. Defaults to the repo VERSION file.

.PARAMETER SkipBuild
  Zip an existing dist\NetPulse folder without running build.bat.

.EXAMPLE
  .\scripts\publish-release.ps1
  .\scripts\publish-release.ps1 -Version 0.1.0
  .\scripts\publish-release.ps1 -SkipBuild
#>
[CmdletBinding()]
param(
  [string] $Version,
  [switch] $SkipBuild
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $Version) {
  $versionFile = Join-Path $repoRoot 'VERSION'
  if (-not (Test-Path $versionFile)) {
    throw "VERSION file not found and -Version was not specified: $versionFile"
  }
  $Version = (Get-Content $versionFile -Raw).Trim()
}

if ($Version -notmatch '^\d+\.\d+\.\d+') {
  throw "Version must look like semver (e.g. 0.1.0): $Version"
}

$distPath = Join-Path $repoRoot 'dist'
$workPath = Join-Path $repoRoot 'build'
$appDir = Join-Path $distPath 'NetPulse'
$exePath = Join-Path $appDir 'NetPulse.exe'
$zipName = "NetPulse-win-x64-v$Version.zip"
$zipPath = Join-Path $distPath $zipName

if (-not $SkipBuild) {
  $env:NETPULSE_NOPAUSE = '1'
  $env:NETPULSE_DISTPATH = $distPath
  $env:NETPULSE_WORKPATH = $workPath

  $buildBat = Join-Path $repoRoot 'build.bat'
  if (-not (Test-Path $buildBat)) {
    throw "build.bat not found: $buildBat"
  }

  Write-Host "Running build.bat (NetPulse.spec -> $appDir) ..."
  $process = Start-Process -FilePath $env:ComSpec -ArgumentList @('/c', "`"$buildBat`"") `
    -WorkingDirectory $repoRoot -Wait -PassThru -NoNewWindow
  if ($process.ExitCode -ne 0) {
    throw "build.bat failed with exit code $($process.ExitCode). See build.log."
  }
}

if (-not (Test-Path $exePath)) {
  throw "Expected folder output missing: $exePath. Run build.bat on Windows first."
}

if (-not (Test-Path $distPath)) {
  New-Item -ItemType Directory -Path $distPath | Out-Null
}

if (Test-Path $zipPath) {
  Remove-Item $zipPath -Force
}

Write-Host "Zipping $appDir -> $zipPath"
# Compress-Archive keeps a top-level NetPulse\ folder inside the zip
Compress-Archive -Path $appDir -DestinationPath $zipPath -CompressionLevel Optimal

$hash = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToUpperInvariant()

Write-Host ""
Write-Host "============================================"
Write-Host " Release artifact ready"
Write-Host "============================================"
Write-Host " File:   $zipPath"
Write-Host " SHA256: $hash"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Create GitHub release tag v$Version and attach $zipName"
Write-Host "  2. Set the SHA256 in pack\chocolatey\netpulse\tools\chocolateyinstall.ps1 to:"
Write-Host "     $hash"
Write-Host "  3. Set the same SHA256 in pack\chocolatey\netpulse\tools\VERIFICATION.txt"
Write-Host "  4. cd pack\chocolatey\netpulse ; choco pack"
Write-Host ""
