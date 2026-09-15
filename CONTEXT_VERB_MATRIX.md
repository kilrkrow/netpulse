# Context-verb matrix (NetPulse Pro)

## Command Center composition (mockup fidelity)

| Region | Role |
|--------|------|
| Status line | Narrative: probing / complete with timeout hop called out |
| Compact overview | Secondary spine (PC..DST), coral timeouts at a glance |
| Story cards (wrap) | Primary mockup-like hop cards with quality + sparkline |
| Dense hop table | Lower ~60% - all hops scannable |
| Hop intel panel | Selected hop detail + timeout explanation |

Auto-select: worst hop (first timeout, else highest RTT) on completion.

## Verbs

| Surface | Verb | Status |
|---------|------|--------|
| Story card / table / intel | Copy address/hostname | live |
| Hop | Copy ASN | hidden until real ASN |
| Hop | Ping / Trace / MTR / Path lab / Whois / Pin / Markdown | live |
| Hop Shift+ | tracert / pathping / ping -t | live |
| Path lab | table verbs + Compare / Mark filtered / Set target | live |
| Footer | copy / DHCP / flush / ARP / capture / probe source | live |
| Empty | Paste&Run / Recent / playbook placeholder | live / stub |
| Progress | Probing hop N + elapsed + Cancel | live |
| Role badges | This PC / LAN / CGNAT / gateway / public / destination | live |
