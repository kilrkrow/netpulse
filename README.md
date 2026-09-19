# NetPulse

A lightweight network diagnostic tool for Windows. Quick ping, traceroute, and domain dossier lookups from your system tray.

**Version:** [0.1.0](VERSION) (first public GitHub release)

## Features

- **Ping** — ICMP ping with response times and packet loss tracking
- **Traceroute** — Multi-hop path analysis to any host
- **Domain Dossier** — Quick domain/IP lookup and information
- **System Tray** — Always accessible, minimal footprint
- **Clean UI** — Simple, responsive interface
- **Real-time Monitoring** — Monitor network connectivity passively

## Building

### Requirements
- Python 3.10 or later
- PyInstaller (for standalone builds)

### Run
```bash
setup.bat
run.bat
```

Or: `python main.py`

### Build standalone (Windows)

`build.bat` / `NetPulse.spec` produce a self-contained folder
(`dist\NetPulse\` when using `scripts\publish-release.ps1`, otherwise
`%TEMP%\NetPulse-dist\NetPulse\` by default).

```bat
build.bat
```

Zip that folder as `NetPulse-win-x64-v0.1.0.zip` (or run the wrapper below).

```powershell
.\scripts\publish-release.ps1
```

The script runs `build.bat`, writes `dist\NetPulse-win-x64-v0.1.0.zip`, and
prints SHA256 for the Chocolatey package.

## Install

### Portable ZIP

Download `NetPulse-win-x64-v0.1.0.zip` from
[Releases](https://github.com/kilrkrow/netpulse/releases/tag/v0.1.0)
after that release is published. Extract and run `NetPulse\NetPulse.exe`.

### Chocolatey

```powershell
choco install netpulse
```

Package sources live under `pack/chocolatey/`. See
[`pack/chocolatey/README.md`](pack/chocolatey/README.md) for pack, push, and
version-bump steps.

## Release notes

### 0.1.0

First Chocolatey-ready GitHub Release:

- Portable Windows x64 ZIP (`NetPulse-win-x64-v0.1.0.zip`) from `build.bat` / `NetPulse.spec`
- Chocolatey package `netpulse` (`pack/chocolatey/netpulse/`)
- `scripts/publish-release.ps1` wraps build + zip + SHA256

Checksums in the Chocolatey install script stay `REPLACE_ME` until the
`v0.1.0` asset is uploaded.

## Usage

1. Launch NetPulse
2. Select diagnostic type (Ping, Traceroute, Domain Dossier)
3. Enter target (hostname or IP)
4. Results display in real-time

## Technical Details

- Built with Python + PySide6
- Uses system `ping` and `tracert` commands
- Lightweight Windows desktop + tray app
- Portable folder executable (PyInstaller COLLECT)

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**. See the LICENSE file for full details.

In summary: You are free to use, modify, and distribute this software, provided that any derivative works are also licensed under GPLv3.

For the full license text, visit: https://www.gnu.org/licenses/gpl-3.0.txt

## Author

Created by Guy Schamp
