# Copies the finished PyInstaller folder into <repo>\release\NetPulse and zips it.
# Called by build.bat after a successful PyInstaller run. Only touches <repo>\release.
param([Parameter(Mandatory=$true)][string]$Dist)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$m = Select-String -Path (Join-Path $repo 'main.py') -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
if (-not $m) { throw 'APP_VERSION not found in main.py' }
$ver = $m.Matches[0].Groups[1].Value
if (-not (Test-Path (Join-Path $Dist 'NetPulse.exe'))) { throw "NetPulse.exe not found in $Dist" }
$rel = Join-Path $repo 'release'
New-Item -ItemType Directory -Force $rel | Out-Null
$dest = Join-Path $rel 'NetPulse'
$zip = Join-Path $rel ("NetPulse-$ver-win64.zip")
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
if (Test-Path $zip) { Remove-Item $zip -Force }
Copy-Item $Dist $dest -Recurse
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($dest, $zip, [IO.Compression.CompressionLevel]::Optimal, $true)
$h = (Get-FileHash $zip -Algorithm SHA256).Hash
Write-Host "Release folder: $dest"
Write-Host "Release zip:    $zip"
Write-Host "SHA256:         $h"
