# Context-verb matrix (NetPulse Pro MVP)

## UX surfaces (juice pass)

| Surface | Notes |
|---------|--------|
| Path overview timeline | Full-width hop dots; click selects; right-click / Shift+right-click verbs on hop |
| Hop detail panel | Selected hop; same context verbs; no ASN N/A spam |
| Footer strip | Unchanged |
| Empty canvas | Unchanged |
| Fat horizontal card row | Removed as primary view (was forcing h-scroll on 15+ hops) |

## Verbs

| Surface | Verb | Status |
|---------|------|--------|
| Hop (overview/detail) | Copy address | live |
| Hop | Copy hostname | live |
| Hop | Copy ASN | hidden until real ASN data |
| Hop | Ping | live |
| Hop | Trace | live |
| Hop | MTR continuous | live-minimal (`ping -t` + Path lab) |
| Hop | Open in Path lab | live |
| Hop | Whois / reverse DNS | live (best-effort; tracert uses -d, PTR in UI) |
| Hop | Pin as watch target | live |
| Hop | Copy as Markdown row | live |
| Hop Shift+ | Copy tracert/pathping/ping -t | live |
| Path lab row | Same + Compare / Mark ICMP-filtered / Set as new target | live |
| Footer | Copy IPv4/IPv6/gateway/DNS | live |
| Footer | Renew DHCP / Flush DNS | live |
| Footer | Show ARP / neighbors | live |
| Footer | Start timed capture | live (Wireshark launch or explain) |
| Footer | Set as default probe source | live |
| Footer Shift+ | CLI copies | live |
| Empty canvas | Paste target & Run / Recent / playbook placeholder | live / stub playbook |
| Live progress | Probing hop N + elapsed + Cancel | live |
| Role badges | This PC / LAN / CGNAT / gateway / public | live (from address) |
| Snapshot toggle | stub | stub |
| Rail placeholders | Coming soon | stub |
