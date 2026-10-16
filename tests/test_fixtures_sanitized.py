"""Fixtures must hold only simulated addresses (privacy: this is a public repo)."""

import glob
import ipaddress
import os
import re

import pytest

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
ALLOWED_PUBLIC = {"1.1.1.1", "8.8.8.8", "8.8.4.4", "9.9.9.9"}
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
CGNAT = ipaddress.ip_network("100.64.0.0/10")


@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(FIX, "*.json"))))
def test_only_simulated_addresses(path):
    text = open(path, encoding="utf-8").read()
    for m in set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text)):
        ip = ipaddress.ip_address(m)
        ok = (m in ALLOWED_PUBLIC or ip.is_private or ip in CGNAT or any(ip in n for n in DOC_NETS))
        assert ok, f"{os.path.basename(path)} contains non-simulated address {m}"
