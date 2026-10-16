"""IP research from free, key-less sources only, with a local SQLite cache.

Sources (each one receives the address being looked up; the UI says so):
  * Team Cymru IP-to-ASN mapping over DNS   https://team-cymru.com/community-services/ip-asn-mapping/
      <reversed-ip>.origin.asn.cymru.com TXT  -> "ASN | prefix | CC | registry | allocated"
      AS<n>.asn.cymru.com TXT                 -> "ASN | CC | registry | allocated | AS name"
  * RDAP registration data, found through the IANA bootstrap files (RFC 9224)
      https://data.iana.org/rdap/ipv4.json  (ipv6.json), then GET <base>ip/<address>
  * Reverse DNS (PTR)

Private, reserved, CGNAT, link-local, loopback, multicast and documentation addresses are never
looked up: lookup() returns a skip reason for them without touching the network or the cache.
"""

from __future__ import annotations

import ipaddress
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from core.rc.db import Database
from core.rc.ipclass import lookup_allowed, skip_reason

TTL_CYMRU = 12 * 3600
TTL_RDAP = 7 * 24 * 3600
TTL_RDNS = 3600
TTL_BOOTSTRAP = 7 * 24 * 3600
TTL_NEGATIVE = 3600

BOOTSTRAP_URLS = {4: "https://data.iana.org/rdap/ipv4.json", 6: "https://data.iana.org/rdap/ipv6.json"}
USER_AGENT = "NetPulse/1.4 (+https://github.com/kilrkrow/netpulse; IP research)"

HttpGet = Callable[[str], Tuple[int, object]]     # url -> (status code, parsed JSON or None)


@dataclass
class IpReport:
    ip: str
    skipped: Optional[str] = None            # clear label when the address is not looked up
    asn: Optional[int] = None
    asn_name: str = ""
    prefix: str = ""
    country: str = ""                        # registry country code (not a location)
    registry: str = ""
    allocated: str = ""
    rdns: Optional[str] = None
    rdns_checked: bool = False
    rdap: Dict[str, object] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)      # source -> message
    cached: Dict[str, bool] = field(default_factory=dict)     # source -> served from cache

    @property
    def has_data(self) -> bool:
        return bool(self.asn or self.rdns or self.rdap)


def default_http_get(url: str) -> Tuple[int, object]:
    import requests
    r = requests.get(url, headers={"Accept": "application/rdap+json, application/json",
                                   "User-Agent": USER_AGENT}, timeout=(5, 12), allow_redirects=True)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, None


def reverse_name(ip: str) -> Tuple[str, str]:
    """(query name, zone) for the Team Cymru origin lookup."""
    a = ipaddress.ip_address(ip)
    if a.version == 4:
        return ".".join(reversed(ip.split("."))) + ".origin.asn.cymru.com", "origin"
    nibbles = a.exploded.replace(":", "")
    return ".".join(reversed(nibbles)) + ".origin6.asn.cymru.com", "origin6"


def parse_cymru_origin(txt: str) -> Dict[str, object]:
    """'13335 | 1.1.1.0/24 | AU | apnic | 2011-08-11'  (origin may list several ASNs)."""
    parts = [p.strip() for p in txt.strip().strip('"').split("|")]
    if len(parts) < 3:
        raise ValueError("unexpected Team Cymru answer")
    asn_tokens = parts[0].split()
    asn = int(asn_tokens[0])
    return {"asn": asn, "all_asns": [int(x) for x in asn_tokens], "prefix": parts[1], "country": parts[2],
            "registry": parts[3] if len(parts) > 3 else "", "allocated": parts[4] if len(parts) > 4 else ""}


def parse_cymru_asn(txt: str) -> Dict[str, object]:
    """'13335 | US | arin | 2010-07-14 | CLOUDFLARENET, US'"""
    parts = [p.strip() for p in txt.strip().strip('"').split("|")]
    if len(parts) < 5:
        raise ValueError("unexpected Team Cymru AS answer")
    return {"asn_name": parts[4]}


def pick_rdap_base(bootstrap: dict, ip: str) -> Optional[str]:
    """Longest-prefix match of ip in an IANA RDAP bootstrap document (RFC 9224 section 5)."""
    addr = ipaddress.ip_address(ip)
    best: Tuple[int, Optional[str]] = (-1, None)
    for entries, urls in bootstrap.get("services", []):
        for cidr in entries:
            try:
                net = ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                continue
            if net.version == addr.version and addr in net and net.prefixlen > best[0]:
                https = [u for u in urls if u.startswith("https://")]
                best = (net.prefixlen, (https or urls)[0])
    return best[1]


def parse_rdap_ip(doc: dict) -> Dict[str, object]:
    """Pick the useful fields out of an RFC 9083 'ip network' object."""
    out: Dict[str, object] = {}
    for k in ("name", "handle", "type", "country", "startAddress", "endAddress", "parentHandle"):
        if doc.get(k):
            out[k] = doc[k]
    cidrs = []
    for c in doc.get("cidr0_cidrs", []) or []:
        pre = c.get("v4prefix") or c.get("v6prefix")
        if pre is not None and "length" in c:
            cidrs.append(f"{pre}/{c['length']}")
    if cidrs:
        out["cidr"] = ", ".join(cidrs)
    ev = {}
    for e in doc.get("events", []) or []:
        if e.get("eventAction") and e.get("eventDate"):
            ev[e["eventAction"]] = str(e["eventDate"])[:10]
    if ev:
        out["events"] = ev

    def vcard_fn(ent) -> Optional[str]:
        for item in (ent.get("vcardArray") or [None, []])[1]:
            if item and item[0] == "fn":
                return item[3]
        return None

    org = None
    for ent in doc.get("entities", []) or []:
        roles = ent.get("roles", [])
        name = vcard_fn(ent)
        if name and ("registrant" in roles or org is None):
            org = name
            if "registrant" in roles:
                break
    if org:
        out["org"] = org
    rem = []
    for r in doc.get("remarks", []) or []:
        for line in r.get("description", []) or []:
            rem.append(str(line))
    if rem:
        out["remarks"] = " ".join(rem)[:400]
    return out


class IpResearch:
    def __init__(self, db: Database, http_get: HttpGet = default_http_get,
                 txt_resolver: Optional[Callable[[str], str]] = None,
                 ptr_resolver: Optional[Callable[[str], Optional[str]]] = None,
                 clock: Callable[[], float] = time.time):
        self.db = db
        self.http_get = http_get
        self.txt_resolver = txt_resolver or self._dns_txt
        self.ptr_resolver = ptr_resolver or self._dns_ptr
        self.clock = clock

    # ------------------------------------------------------------------ cache
    def _cache_get(self, ip: str, source: str, allow_expired: bool = False) -> Optional[dict]:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT expires_ts, data_json FROM ip_cache WHERE ip=? AND source=?", (ip, source)).fetchone()
        if row is None:
            return None
        if row["expires_ts"] < self.clock() and not allow_expired:
            return None
        return json.loads(row["data_json"])

    def _cache_put(self, ip: str, source: str, data: dict, ttl: float) -> None:
        now = self.clock()
        with self.db.lock:
            self.db.conn.execute(
                "INSERT OR REPLACE INTO ip_cache(ip,source,fetched_ts,expires_ts,data_json) VALUES (?,?,?,?,?)",
                (ip, source, now, now + ttl, json.dumps(data)))

    def _kv_get(self, key: str, ttl: float) -> Optional[dict]:
        with self.db.lock:
            row = self.db.conn.execute("SELECT value, fetched_ts FROM kv WHERE key=?", (key,)).fetchone()
        if row and self.clock() - row["fetched_ts"] < ttl:
            return json.loads(row["value"])
        return None

    def _kv_put(self, key: str, value: dict) -> None:
        with self.db.lock:
            self.db.conn.execute("INSERT OR REPLACE INTO kv(key,value,fetched_ts) VALUES (?,?,?)",
                                 (key, json.dumps(value), self.clock()))

    def cached_asn(self, ip: str) -> Optional[int]:
        """ASN from the local cache only. Never touches the network."""
        if not lookup_allowed(ip):
            return None
        d = self._cache_get(ip, "cymru", allow_expired=True)
        return int(d["asn"]) if d and d.get("asn") else None

    def clear_cache(self) -> None:
        with self.db.lock:
            self.db.conn.execute("DELETE FROM ip_cache")
            self.db.conn.execute("DELETE FROM kv")

    # ------------------------------------------------------------------ DNS
    @staticmethod
    def _resolver():
        import dns.resolver
        r = dns.resolver.Resolver()
        r.timeout = 3.0
        r.lifetime = 5.0
        return r

    def _dns_txt(self, name: str) -> str:
        ans = self._resolver().resolve(name, "TXT")
        rdata = ans[0]
        return b"".join(rdata.strings).decode("ascii", "replace")

    def _dns_ptr(self, ip: str) -> Optional[str]:
        import dns.resolver
        try:
            ans = self._resolver().resolve_address(ip)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return None
        return str(ans[0]).rstrip(".")

    # ------------------------------------------------------------------ sources
    def _src_cymru(self, ip: str, rep: IpReport, force: bool) -> None:
        data = None if force else self._cache_get(ip, "cymru")
        if data is not None:
            rep.cached["cymru"] = True
        else:
            try:
                qname, _zone = reverse_name(ip)
                origin = parse_cymru_origin(self.txt_resolver(qname))
                try:
                    origin.update(parse_cymru_asn(self.txt_resolver(f"AS{origin['asn']}.asn.cymru.com")))
                except Exception:
                    origin.setdefault("asn_name", "")
                data = origin
                self._cache_put(ip, "cymru", data, TTL_CYMRU)
            except Exception as exc:
                name = exc.__class__.__name__
                if name in ("NXDOMAIN", "NoAnswer"):
                    self._cache_put(ip, "cymru", {"none": True}, TTL_NEGATIVE)
                    rep.errors["cymru"] = "Team Cymru has no origin ASN for this address."
                else:
                    rep.errors["cymru"] = f"Team Cymru DNS lookup failed ({name}); the network or DNS may block it."
                return
        if data.get("none"):
            rep.errors["cymru"] = "Team Cymru has no origin ASN for this address."
            return
        rep.asn = int(data["asn"])
        rep.asn_name = str(data.get("asn_name", ""))
        rep.prefix = str(data.get("prefix", ""))
        rep.country = str(data.get("country", ""))
        rep.registry = str(data.get("registry", ""))
        rep.allocated = str(data.get("allocated", ""))

    def _src_rdns(self, ip: str, rep: IpReport, force: bool) -> None:
        data = None if force else self._cache_get(ip, "rdns")
        if data is not None:
            rep.cached["rdns"] = True
        else:
            try:
                name = self.ptr_resolver(ip)
            except Exception as exc:
                rep.errors["rdns"] = f"Reverse DNS failed ({exc.__class__.__name__})."
                return
            data = {"name": name}
            self._cache_put(ip, "rdns", data, TTL_RDNS)
        rep.rdns = data.get("name")
        rep.rdns_checked = True

    def _bootstrap(self, version: int) -> Optional[dict]:
        key = f"rdap-bootstrap-v{version}"
        doc = self._kv_get(key, TTL_BOOTSTRAP)
        if doc is None:
            status, body = self.http_get(BOOTSTRAP_URLS[version])
            if status == 200 and isinstance(body, dict):
                self._kv_put(key, body)
                doc = body
        return doc

    def _src_rdap(self, ip: str, rep: IpReport, force: bool) -> None:
        data = None if force else self._cache_get(ip, "rdap")
        if data is not None:
            rep.cached["rdap"] = True
        else:
            try:
                version = ipaddress.ip_address(ip).version
                base = None
                try:
                    doc = self._bootstrap(version)
                    base = pick_rdap_base(doc, ip) if doc else None
                except Exception:
                    base = None
                url = (base + f"ip/{ip}") if base else f"https://rdap.org/ip/{ip}"
                status, body = self.http_get(url)
                if status == 404:
                    rep.errors["rdap"] = "RDAP has no registration record for this address."
                    return
                if status != 200 or not isinstance(body, dict):
                    rep.errors["rdap"] = f"RDAP server answered HTTP {status}."
                    return
                data = parse_rdap_ip(body)
                data["server"] = url.split("/ip/")[0]
                self._cache_put(ip, "rdap", data, TTL_RDAP)
            except Exception as exc:
                rep.errors["rdap"] = f"RDAP lookup failed ({exc.__class__.__name__}); the network may block it."
                return
        rep.rdap = data

    # ------------------------------------------------------------------ public
    def lookup(self, ip: str, force: bool = False) -> IpReport:
        rep = IpReport(ip=ip)
        reason = skip_reason(ip)
        if reason:
            rep.skipped = reason
            return rep
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(self._src_cymru, ip, rep, force),
                    ex.submit(self._src_rdns, ip, rep, force),
                    ex.submit(self._src_rdap, ip, rep, force)]
            for f in futs:
                f.result()
        return rep
