$ErrorActionPreference = 'Stop'

Uninstall-BinFile -Name 'NetPulse'
$installDir = "$env:ProgramFiles\NetPulse"
if (Test-Path $installDir) { Remove-Item $installDir -Recurse -Force }
