"""Domain dossier: DNS, GeoIP, WHOIS lookups in background threads."""

import itertools
import socket
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal

try:
    import dns.exception
    import dns.resolver

    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

try:
    import whois

    WHOIS_AVAILABLE = True
except ImportError:
    WHOIS_AVAILABLE = False

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


@dataclass
class DnsRecord:
    rtype: str
    ttl: int
    value: str


@dataclass
class GeoInfo:
    ip: str
    country: str = ""
    country_code: str = ""
    region: str = ""
    city: str = ""
    isp: str = ""
    org: str = ""
    asn: str = ""
    lat: float = 0.0
    lon: float = 0.0
    timezone: str = ""


@dataclass
class WhoisInfo:
    domain: str = ""
    registrar: str = ""
    creation_date: str = ""
    expiration_date: str = ""
    updated_date: str = ""
    name_servers: List[str] = field(default_factory=list)
    status: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    registrant_name: str = ""
    registrant_org: str = ""
    registrant_country: str = ""


@dataclass
class DossierResult:
    target: str
    resolved_ip: Optional[str] = None
    reverse_dns: Optional[str] = None
    dns_records: List[DnsRecord] = field(default_factory=list)
    geo: Optional[GeoInfo] = None
    whois_info: Optional[WhoisInfo] = None
    errors: Dict[str, str] = field(default_factory=dict)


def _fmt_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = value[0]
    try:
        return value.strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def _resolve_ip(target: str) -> Optional[str]:
    try:
        return socket.gethostbyname(target)
    except Exception:
        return None


def _reverse_dns(ip: str) -> Optional[str]:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def _get_dns_records(target: str) -> tuple[List[DnsRecord], dict]:
    records: List[DnsRecord] = []
    errors: dict = {}
    if not DNS_AVAILABLE:
        errors["dns"] = "dnspython not installed"
        return records, errors

    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 10

    for rtype in ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"):
        try:
            answers = resolver.resolve(target, rtype)
            for rdata in answers:
                ttl = answers.rrset.ttl if answers.rrset else 0
                records.append(DnsRecord(rtype=rtype, ttl=ttl, value=str(rdata)))
        except dns.resolver.NXDOMAIN:
            errors["dns_nxdomain"] = f"{target} does not exist"
            break
        except dns.exception.DNSException:
            pass
        except Exception as exc:
            errors[f"dns_{rtype}"] = str(exc)

    return records, errors


def _get_geoip(ip: str) -> tuple[Optional[GeoInfo], Optional[str]]:
    if not REQUESTS_AVAILABLE:
        return None, "requests not installed"
    try:
        response = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={
                "fields": "status,country,countryCode,regionName,city,isp,org,as,lat,lon,timezone"
            },
            timeout=10,
        )
        data = response.json()
        if data.get("status") == "success":
            return (
                GeoInfo(
                    ip=ip,
                    country=data.get("country", ""),
                    country_code=data.get("countryCode", ""),
                    region=data.get("regionName", ""),
                    city=data.get("city", ""),
                    isp=data.get("isp", ""),
                    org=data.get("org", ""),
                    asn=data.get("as", ""),
                    lat=data.get("lat", 0.0),
                    lon=data.get("lon", 0.0),
                    timezone=data.get("timezone", ""),
                ),
                None,
            )
        return None, data.get("message", "GeoIP lookup failed")
    except Exception as exc:
        return None, str(exc)


def _get_whois(target: str) -> tuple[Optional[WhoisInfo], Optional[str]]:
    if not WHOIS_AVAILABLE:
        return None, "python-whois not installed"
    try:
        result = whois.whois(target)

        def listify(value):
            if value is None:
                return []
            return value if isinstance(value, list) else [value]

        return (
            WhoisInfo(
                domain=str(result.get("domain_name", target)),
                registrar=str(result.get("registrar", "")),
                creation_date=_fmt_date(result.get("creation_date")),
                expiration_date=_fmt_date(result.get("expiration_date")),
                updated_date=_fmt_date(result.get("updated_date")),
                name_servers=[str(item).lower() for item in listify(result.get("name_servers"))],
                status=[str(item) for item in listify(result.get("status"))],
                emails=[str(item) for item in listify(result.get("emails"))],
                registrant_name=str(result.get("name", "")),
                registrant_org=str(result.get("org", "")),
                registrant_country=str(result.get("country", "")),
            ),
            None,
        )
    except Exception as exc:
        return None, str(exc)


class DossierEngine(QObject):
    """Run dossier lookups in background threads; emit partial results as they arrive."""

    ip_resolved = Signal(int, str, str)
    reverse_dns_ready = Signal(int, str, str)
    dns_records_ready = Signal(int, str, list)
    geo_ready = Signal(int, str, object)
    whois_ready = Signal(int, str, object)
    error_occurred = Signal(int, str, str)
    finished = Signal(int, object)

    def __init__(self):
        super().__init__()
        self._request_ids = itertools.count(1)

    def lookup(self, target: str) -> int:
        request_id = next(self._request_ids)
        threading.Thread(
            target=self._do_lookup,
            args=(request_id, target),
            daemon=True,
        ).start()
        return request_id

    def _do_lookup(self, request_id: int, target: str):
        result = DossierResult(target=target)

        ip = _resolve_ip(target)
        if ip:
            result.resolved_ip = ip
            self.ip_resolved.emit(request_id, target, ip)
        else:
            self.error_occurred.emit(request_id, "resolve", f"Could not resolve {target}")

        if ip:
            reverse_dns = _reverse_dns(ip)
            if reverse_dns:
                result.reverse_dns = reverse_dns
                self.reverse_dns_ready.emit(request_id, target, reverse_dns)

        records, dns_errors = _get_dns_records(target)
        result.dns_records = records
        result.errors.update(dns_errors)
        self.dns_records_ready.emit(request_id, target, records)

        if ip:
            geo, geo_error = _get_geoip(ip)
            if geo:
                result.geo = geo
                self.geo_ready.emit(request_id, target, geo)
            elif geo_error:
                self.error_occurred.emit(request_id, "geoip", geo_error)

        whois_info, whois_error = _get_whois(target)
        if whois_info:
            result.whois_info = whois_info
            self.whois_ready.emit(request_id, target, whois_info)
        elif whois_error:
            self.error_occurred.emit(request_id, "whois", whois_error)

        self.finished.emit(request_id, result)
