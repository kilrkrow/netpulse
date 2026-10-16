# NetPulse

A network diagnostic tool for Windows that lives in the system tray. It answers one question first: **which part of my connection is broken?** Then it keeps the classic tools (ping monitor, traceroute, domain dossier, alerts) one click away.

## Root-cause view

NetPulse maps the path from this PC to a stable target (1.1.1.1 by default), probes every hop continuously with ICMP and labels each hop as **this PC**, **gateway**, **Starlink dish** or **wider internet**.

- **Path map** - a row of instrument cells, one per hop, with live latency, loss and jitter, VFD meters and a 60 second phosphor trace. Click a hop for a 5 minute graph.
- **Verdict** - a plain-English diagnosis above the path ("Dish is down: your router is fine, the Starlink link is not") with the evidence listed under it. Rules are simple and visible: the first lossy hop is the suspect, and loss that shows on one hop while every later hop is clean is treated as ICMP rate-limiting, not a fault. When the evidence is thin NetPulse says **"Can't tell"** instead of guessing.
- **Disconnect log** - every outage is stored in a local SQLite file (start, duration, failing segment). The log survives restarts. **Copy report** puts a plain-text summary on the clipboard for support calls.
- **IP research** - click a hop or type an address to see ASN, owner, registry country, reverse DNS and RDAP registration. Only free, key-less sources are used (Team Cymru DNS, RDAP via the IANA bootstrap, reverse DNS). Results are cached locally with a TTL. Private, LAN, carrier-grade NAT (100.64.0.0/10), link-local and documentation addresses are **never** looked up. The first time, NetPulse tells you that lookups send the address to those services and asks you to allow them.
- **Your labels win** - right-click a hop to label it Gateway, Dish or Internet. Labels are saved.

Everything runs unprivileged. Probes use the Windows ICMP API (`IcmpSendEcho`) directly, so no administrator rights, no raw sockets and no helper console windows are needed. No router login is used.

Dish detection: CGNAT addresses (100.64.0.0/10), the dish at `192.168.100.1` when reachable, and hops whose owner is Starlink (AS14593, only after you allow lookups).

### Tray

Right-click the tray icon for the current status, **Copy report**, **Start with Windows**, **Add to Start menu**, **Settings...**, **About** and **Exit**. Closing the window keeps NetPulse running in the tray; **Exit NetPulse** quits it completely. `NetPulse.exe --background` starts hidden in the tray (this is what **Start with Windows** registers).

### Where data lives

`%LOCALAPPDATA%\NetPulse\` holds `netpulse.db` (outage log and lookup cache) and `settings.json`. The older ping/dossier history stays in `%APPDATA%\NetPulse\history.json`. Nothing is written to the program folder.

## Classic tools

- **Monitor** - ICMP ping sessions with response times and packet loss, per-process connection watching
  (the ping Interval, Timeout and Graph length for new sessions are in **Settings**, the button at the right end of the tab row)
- **Traceroute** - multi-hop path analysis to any host
- **Dossier** - DNS, GeoIP and WHOIS for a domain or IP
- **Alerts** - configurable latency, loss and jitter rules with tray notifications

## Run from source

```bash
pip install -r requirements.txt
python main.py
```

Python 3.10 or later on Windows. For development: `pip install pytest` then `python -m pytest`.

### Simulation (developers)

Feed a scripted network into the real UI without touching your own network:

```bash
python main.py --simulate dish-outage
```

Scenarios: `healthy`, `gateway-outage`, `dish-outage`, `internet-outage`, `cant-tell`, `loss`, `latency`, `ratelimit`, `measuring`, `history`. The environment variable `NETPULSE_SIMULATE` does the same. Simulated runs use their own database and settings files and are labeled "SIMULATED DATA" in the status bar. There is no simulation menu in the UI.

## Build the executable

```bash
build.bat
```

This wraps PyInstaller with `NetPulse.spec` and writes `%TEMP%\NetPulse-dist\NetPulse\NetPulse.exe`.

## Tests

```bash
python -m pytest
```

Unit tests cover the probe engine, hop labeling, the verdict rules (against simulated and sanitized recorded traces in `tests/fixtures`), the outage log, IP research (with fake DNS/HTTP), settings and the Windows autostart entries. A smoke test runs the real window against simulated networks and checks every visible label is plain ASCII.

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**. See the LICENSE file for full details.

In summary: You are free to use, modify, and distribute this software, provided that any derivative works are also licensed under GPLv3.

For the full license text, visit: https://www.gnu.org/licenses/gpl-3.0.txt

## Author

Created by Guy Schamp
