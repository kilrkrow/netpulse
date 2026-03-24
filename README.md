# NetPulse

A lightweight network diagnostic tool for Windows. Quick ping, traceroute, and domain dossier lookups from your system tray.

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
python netpulse.py
```

### Build Standalone
```bash
pyinstaller netpulse.spec
```

## Usage

1. Launch NetPulse
2. Select diagnostic type (Ping, Traceroute, Domain Dossier)
3. Enter target (hostname or IP)
4. Results display in real-time

## Technical Details

- Built with Python + tkinter
- Uses system `ping` and `traceroute` commands
- Lightweight, cross-platform compatible
- Single-file executable available

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**. See the LICENSE file for full details.

In summary: You are free to use, modify, and distribute this software, provided that any derivative works are also licensed under GPLv3.

For the full license text, visit: https://www.gnu.org/licenses/gpl-3.0.txt

## Author

Created by Guy Schamp
