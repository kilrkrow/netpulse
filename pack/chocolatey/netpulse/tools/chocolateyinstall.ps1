$ErrorActionPreference = 'Stop'
$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$version = '0.1.0'
$packageName = 'netpulse'
$zipName = "NetPulse-win-x64-v$version.zip"
$baseUrl = "https://github.com/kilrkrow/netpulse/releases/download/v$version"
$zipUrl = "$baseUrl/$zipName"
$zipPath = Join-Path $toolsDir $zipName

# SHA256 of the official v0.1.0 GitHub release asset
# https://github.com/kilrkrow/netpulse/releases/download/v0.1.0/NetPulse-win-x64-v0.1.0.zip
$checksum = '7E70150890FAD6670C23A06F7F91D6CD864F63020D4CA7EC0AEFD4E0895BCE88'

Get-ChocolateyWebFile -PackageName $packageName -FileFullPath $zipPath -Url $zipUrl `
  -Checksum $checksum -ChecksumType 'sha256'

Get-ChocolateyUnzip -FileFullPath $zipPath -Destination $toolsDir -PackageName $packageName

$exe = Get-ChildItem -Path $toolsDir -Filter 'NetPulse.exe' -Recurse -File |
  Where-Object { $_.FullName -notmatch '\\(_rels|package)\\' } |
  Select-Object -First 1

if (-not $exe) {
  throw "NetPulse.exe not found after unzipping $zipName into $toolsDir"
}

$exePath = $exe.FullName
$workDir = $exe.DirectoryName

# GUI app: UseStart so the shim does not block the console
Install-BinFile -Name 'netpulse' -Path $exePath -UseStart

$shortcut = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\NetPulse.lnk'
Install-ChocolateyShortcut -ShortcutFilePath $shortcut -TargetPath $exePath -WorkingDirectory $workDir `
  -IconLocation $exePath -Description 'NetPulse network diagnostics'

Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
