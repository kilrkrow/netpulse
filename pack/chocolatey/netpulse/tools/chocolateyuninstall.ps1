$ErrorActionPreference = 'Stop'

Uninstall-BinFile -Name 'netpulse'

$shortcut = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\NetPulse.lnk'
if (Test-Path $shortcut) {
  Remove-Item $shortcut -Force -ErrorAction SilentlyContinue
}
