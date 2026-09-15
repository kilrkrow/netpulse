# Context-verb matrix (NetPulse Pro MVP)

| Surface | Verb | Status |
|---------|------|--------|
| Hop card | Copy address | live |
| Hop card | Copy hostname | live |
| Hop card | Copy ASN | stub (N/A until free ASN source) |
| Hop card | Ping | live (opens console ping) |
| Hop card | Trace | live (re-runs Path) |
| Hop card | MTR continuous | live-minimal (`ping -t` + Path lab) |
| Hop card | Open in Path lab | live |
| Hop card | Whois / reverse DNS | live (best-effort) |
| Hop card | Pin as watch target | live (AppData JSON) |
| Hop card | Copy as Markdown row | live |
| Hop card Shift+ | Copy tracert/pathping/ping -t | live |
| Path lab row | Same as hop + Compare / Mark ICMP-filtered / Set as new target | live |
| Footer | Copy IPv4/IPv6/gateway/DNS | live |
| Footer | Renew DHCP | live (elevation may fail gracefully) |
| Footer | Flush DNS | live |
| Footer | Show ARP/neighbors | live |
| Footer | Start timed capture | live (launch Wireshark or explain) |
| Footer | Set as default probe source | live (persist iface) |
| Footer Shift+ | Copy ipconfig/netsh/arp CLI | live |
| Empty canvas | Paste target & Run | live |
| Empty canvas | Recent targets | live |
| Empty canvas | Can't reach internet playbook | stub (navigates Playbooks placeholder) |
| Rail Link/DNS/Ports/Capture/Playbooks | pages | stub Coming soon |
| Snapshot toggle | mode | stub (keeps last path for Compare) |
