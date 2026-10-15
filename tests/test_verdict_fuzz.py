"""Randomized checks: a noisy but healthy network never raises an alarm, and a single injected fault is never
pinned on the wrong segment."""

import random

import pytest

from core.rc.model import KIND_DEGRADED, KIND_HEALTHY, KIND_MEASURING, KIND_OUTAGE, KIND_UNKNOWN
from core.rc.verdict import VerdictEngine
from tests.fixture_loader import make_trace

HOPS = [(1, "192.168.1.1", "gateway", False, 1.2),
        (2, "100.64.0.1", "dish", False, 28.0),
        (3, "198.51.100.1", "internet", False, 30.0),
        (4, "198.51.100.17", "internet", False, 31.0),
        (5, "203.0.113.9", "internet", False, 33.0),
        (6, "1.1.1.1", "internet", True, 34.0)]


def noisy(rng, base, loss=0.0, spike_p=0.0):
    def f(_i):
        if rng.random() < loss:
            return False, None
        v = max(0.3, rng.gauss(base, base * 0.08))
        if rng.random() < spike_p:
            v *= rng.uniform(2.0, 4.0)
        return True, v
    return f


@pytest.mark.parametrize("seed", range(300))
def test_noisy_healthy_network_never_alarms(seed):
    rng = random.Random(seed)
    spec = []
    for ttl, ip, seg, tgt, base in HOPS:
        # background loss up to 2 percent, rare single spikes
        spec.append((ttl, ip, seg, tgt, noisy(rng, base, loss=rng.uniform(0, 0.02), spike_p=0.02)))
    v = VerdictEngine().evaluate(make_trace(spec, n=300))
    assert v.kind in (KIND_HEALTHY, KIND_MEASURING), (seed, v.kind, v.headline)


@pytest.mark.parametrize("seed", range(6))
def test_one_rate_limiting_router_is_not_a_fault(seed):
    rng = random.Random(100 + seed)
    spec = []
    for ttl, ip, seg, tgt, base in HOPS:
        loss = rng.uniform(0.25, 0.6) if ttl == 4 else 0.0
        spec.append((ttl, ip, seg, tgt, noisy(rng, base, loss=loss)))
    v = VerdictEngine().evaluate(make_trace(spec, n=300))
    assert v.kind == KIND_HEALTHY, (seed, v.kind, v.headline)


@pytest.mark.parametrize("fault_ttl", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("seed", range(8))
def test_injected_outage_is_attributed_to_the_right_segment(fault_ttl, seed):
    rng = random.Random(1000 * fault_ttl + seed)
    down_for = rng.randint(12, 40)
    spec = []
    for ttl, ip, seg, tgt, base in HOPS:
        f = noisy(rng, base, loss=rng.uniform(0, 0.02))
        if ttl >= fault_ttl:
            spec.append((ttl, ip, seg, tgt,
                         (lambda f_: (lambda i: (False, None) if i >= 300 - down_for else f_(i)))(f)))
        else:
            spec.append((ttl, ip, seg, tgt, f))
    v = VerdictEngine().evaluate(make_trace(spec, n=300))
    expected = HOPS[fault_ttl - 1][2]
    assert v.kind == KIND_OUTAGE, (fault_ttl, seed, v.kind, v.headline)
    assert v.segment == expected, (fault_ttl, seed, v.segment, v.headline)


@pytest.mark.parametrize("seed", range(10))
def test_target_only_failure_never_blames_a_middle_segment(seed):
    rng = random.Random(5000 + seed)
    spec = []
    for ttl, ip, seg, tgt, base in HOPS:
        f = noisy(rng, base)
        if tgt:
            spec.append((ttl, ip, seg, tgt, lambda i, f_=f: (False, None) if i >= 280 else f_(i)))
        else:
            spec.append((ttl, ip, seg, tgt, f))
    v = VerdictEngine().evaluate(make_trace(spec, n=300))
    assert v.segment in (None, "internet"), (seed, v.segment, v.headline)
    assert v.kind in (KIND_OUTAGE, KIND_UNKNOWN, KIND_DEGRADED)
