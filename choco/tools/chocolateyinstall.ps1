$ErrorActionPreference = 'Stop'

$packageArgs = @{
  packageName   = $env:ChocolateyPackageName
  url           = 'https://github.com/kilrkrow/netpulse/releases/download/v__VERSION__/NetPulse-__VERSION__-win64.zip'
  checksum      = '__CHECKSUM__'
  checksumType  = 'sha256'
  unzipLocation = $env:ProgramFiles
}

Install-ChocolateyZipPackage @packageArgs
# Shim only the main exe; PySide6 ships many internal exes we don't want on PATH
Install-BinFile -Name 'NetPulse' -Path "$env:ProgramFiles\NetPulse\NetPulse.exe"
