"""IP research: classification gate, Team Cymru / RDAP parsing, cache with TTL (all offline, fakes)."""

import json

import pytest

from core.rc.db import Database
from core.rc.ipinfo import (IpResearch, parse_cymru_asn, parse_cymru_origin, parse_rdap_ip, pick_rdap_base,
                            reverse_name)

BOOT = {"services": [[["1.0.0.0/8", "14.0.0.0/8"], ["https://rdap.apnic.net/"]],
                     [["8.0.0.0/8", "192.0.0.0/8"], ["http://rdap.arin.net/registry/", "https://rdap.arin.net/registry/"]],
                     [["8.8.4.0/24"], ["https://rdap.example.net/special/"]]]}

RDAP_CF = {"name": "APNIC-LABS", "handle": "1.1.1.0 - 1.1.1.255", "type": "ASSIGNED PORTABLE", "country": "AU",
           "startAddress": "1.1.1.0", "endAddress": "1.1.1.255",
           "events": [{"eventAction": "registration", "eventDate": "2011-08-10T23:12:35Z"},
                      {"eventAction": "last changed", "eventDate": "2023-04-26T22:57:58Z"}],
           "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [["fn", {}, "text", "IRT-APNICRANDNET-AU"]]]},
                        {"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "Example Org"]]]}],
           "remarks": [{"description": ["Used for research"]}]}


class Fake:
    def __init__(self):
        self.dns_calls, self.http_calls, self.ptr_calls = [], [], []
        self.now = 1_000_000.0

    def txt(self, name):
        self.dns_calls.append(name)
        if name == "1.1.1.1.origin.asn.cymru.com":
            return "13335 | 1.1.1.0/24 | AU | apnic | 2011-08-11"
        if name == "AS13335.asn.cymru.com":
            return "13335 | US | arin | 2010-07-14 | CLOUDFLARENET, US"
        if name == "8.8.8.8.origin.asn.cymru.com":
            return "15169 | 8.8.8.0/24 | US | arin | 2023-12-28"
        if name == "AS15169.asn.cymru.com":
            return "15169 | US | arin | 2000-03-30 | GOOGLE, US"
        raise RuntimeError("no such name " + name)

    def ptr(self, ip):
        self.ptr_calls.append(ip)
        return {"1.1.1.1": "one.one.one.one", "8.8.8.8": "dns.google"}.get(ip)

    def http(self, url):
        self.http_calls.append(url)
        if url.endswith("ipv4.json"):
            return 200, BOOT
        if "/ip/1.1.1.1" in url:
            assert url == "https://rdap.apnic.net/ip/1.1.1.1"
            return 200, RDAP_CF
        if "/ip/8.8.8.8" in url:
            assert url.startswith("https://rdap.arin.net/registry/ip/")
            return 200, {"name": "GOGL", "handle": "NET-8-8-8-0-2", "country": "US", "entities": [],
                         "cidr0_cidrs": [{"v4prefix": "8.8.8.0", "length": 24}]}
        return 404, None


@pytest.fixture
def research(tmp_path):
    f = Fake()
    r = IpResearch(Database(str(tmp_path / "c.db")), http_get=f.http, txt_resolver=f.txt, ptr_resolver=f.ptr,
                   clock=lambda: f.now)
    return r, f


def test_known_addresses_resolve_to_the_right_asn_and_org(research):
    r, _ = research
    cf = r.lookup("1.1.1.1")
    assert cf.asn == 13335 and "CLOUDFLARE" in cf.asn_name and cf.prefix == "1.1.1.0/24"
    assert cf.rdns == "one.one.one.one" and cf.rdap["name"] == "APNIC-LABS" and cf.rdap["org"] == "Example Org"
    assert cf.rdap["events"]["registration"] == "2011-08-10"
    g = r.lookup("8.8.8.8")
    assert g.asn == 15169 and "GOOGLE" in g.asn_name and g.rdns == "dns.google" and g.rdap["cidr"] == "8.8.8.0/24"
    assert not cf.errors and not g.errors


@pytest.mark.parametrize("ip", ["192.168.1.1", "10.0.0.5", "172.20.1.1", "100.64.0.1", "169.254.1.1", "127.0.0.1",
                                "192.0.2.4", "198.51.100.17", "203.0.113.9", "224.0.0.1", "garbage"])
def test_non_public_addresses_are_skipped_and_never_leave_the_machine(research, ip):
    r, f = research
    rep = r.lookup(ip)
    assert rep.skipped and "Not looked up" in rep.skipped
    assert not f.dns_calls and not f.http_calls and not f.ptr_calls
    assert r.cached_asn(ip) is None


def test_cache_serves_repeats_and_expires_by_ttl(research):
    r, f = research
    r.lookup("1.1.1.1")
    n_dns, n_http = len(f.dns_calls), len(f.http_calls)
    again = r.lookup("1.1.1.1")
    assert len(f.dns_calls) == n_dns and len(f.http_calls) == n_http
    assert all(again.cached.get(k) for k in ("cymru", "rdap", "rdns"))
    assert r.cached_asn("1.1.1.1") == 13335
    f.now += 3600 * 2            # past the 1 h reverse-DNS TTL only
    r.lookup("1.1.1.1")
    assert len(f.ptr_calls) == 2 and len(f.dns_calls) == n_dns
    f.now += 3600 * 13           # past the 12 h Team Cymru TTL
    r.lookup("1.1.1.1")
    assert len(f.dns_calls) > n_dns


def test_cache_survives_reopen(tmp_path):
    f = Fake()
    path = str(tmp_path / "c.db")
    IpResearch(Database(path), http_get=f.http, txt_resolver=f.txt, ptr_resolver=f.ptr, clock=lambda: f.now).lookup("8.8.8.8")
    calls = len(f.dns_calls)
    r2 = IpResearch(Database(path), http_get=f.http, txt_resolver=f.txt, ptr_resolver=f.ptr, clock=lambda: f.now)
    assert r2.lookup("8.8.8.8").asn == 15169 and len(f.dns_calls) == calls


def test_blocked_services_are_reported_honestly_and_not_cached(research):
    r, f = research

    def boom(name):
        raise OSError("dns blocked")
    r.txt_resolver = boom
    rep = r.lookup("1.1.1.1")
    assert rep.asn is None and "Team Cymru DNS lookup failed" in rep.errors["cymru"]
    assert rep.rdap and rep.rdns          # the other sources still answer
    r.txt_resolver = f.txt
    assert r.lookup("1.1.1.1").asn == 13335   # the failure was not cached


def test_parsers_and_bootstrap_longest_prefix():
    assert parse_cymru_origin('"13335 | 1.1.1.0/24 | AU | apnic | 2011-08-11"')["asn"] == 13335
    assert parse_cymru_origin("64512 64513 | 10.0.0.0/8 | ZZ | x |")["all_asns"] == [64512, 64513]
    assert parse_cymru_asn("15169 | US | arin | 2000-03-30 | GOOGLE, US")["asn_name"] == "GOOGLE, US"
    assert reverse_name("1.2.3.4")[0] == "4.3.2.1.origin.asn.cymru.com"
    assert reverse_name("2001:db8::1")[1] == "origin6"
    assert pick_rdap_base(BOOT, "8.8.4.4") == "https://rdap.example.net/special/"
    assert pick_rdap_base(BOOT, "8.8.8.8") == "https://rdap.arin.net/registry/"      # https preferred, longest match
    assert pick_rdap_base(BOOT, "9.9.9.9") is None
    assert parse_rdap_ip(RDAP_CF)["org"] == "Example Org"


def test_bootstrap_is_cached(research):
    r, f = research
    r.lookup("1.1.1.1")
    r.lookup("8.8.8.8")
    assert sum(1 for u in f.http_calls if u.endswith("ipv4.json")) == 1
