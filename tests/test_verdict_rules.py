"""Verdict rules against recorded and simulated traces (tests/fixtures) and hand-made patterns."""

import pytest

from core.rc.model import (KIND_DEGRADED, KIND_HEALTHY, KIND_MEASURING, KIND_OUTAGE, KIND_UNKNOWN, SEG_DISH,
                           SEG_GATEWAY, SEG_INTERNET, STATUS_INFO, Evidence, Finding)
from core.rc.verdict import VerdictEngine
from tests.fixture_loader import load_snapshot, make_trace

# fixture -> (kind, segment, rule, words that must be in headline+explanation)
SCENARIO_TABLE = [
    ("sim_healthy.json", KIND_HEALTHY, None, "healthy", ["healthy"]),
    ("sim_gateway_outage.json", KIND_OUTAGE, SEG_GATEWAY, "outage", ["router", "stopped answering"]),
    ("sim_dish_outage.json", KIND_OUTAGE, SEG_DISH, "outage", ["Starlink", "dish"]),
    ("sim_internet_outage.json", KIND_OUTAGE, SEG_INTERNET, "outage", ["internet"]),
    ("sim_cant_tell.json", KIND_UNKNOWN, None, "target-only-unmapped", ["Can't tell"]),
    ("sim_measuring.json", KIND_MEASURING, None, "measuring", ["Can't tell yet"]),
    ("sim_loss.json", KIND_DEGRADED, SEG_DISH, "loss", ["Packet loss", "Starlink"]),
    ("sim_latency.json", KIND_DEGRADED, SEG_INTERNET, "latency", ["Latency spike"]),
    ("sim_ratelimit.json", KIND_HEALTHY, None, "healthy", ["healthy"]),
    ("recorded_starlink_ratelimit.json", KIND_HEALTHY, None, "healthy", ["healthy"]),
]


@pytest.mark.parametrize("fixture,kind,segment,rule,words", SCENARIO_TABLE)
def test_fixture_verdicts(fixture, kind, segment, rule, words):
    v = VerdictEngine().evaluate(load_snapshot(fixture))
    assert v.kind == kind, (v.headline, v.explanation)
    assert v.segment == segment
    assert v.rule == rule
    text = v.headline + " " + v.explanation
    for w in words:
        assert w.lower() in text.lower()


def test_healthy_network_has_no_false_alarm_and_no_fault_evidence():
    v = VerdictEngine().evaluate(load_snapshot("sim_healthy.json"))
    assert v.kind == KIND_HEALTHY and not v.disconnect
    assert all(e.status != "fail" for e in v.evidence)


def test_rate_limited_hop_is_not_a_fault_and_is_explained():
    v = VerdictEngine().evaluate(load_snapshot("sim_ratelimit.json"))
    assert v.kind == KIND_HEALTHY
    notes = [e for e in v.evidence if e.kind == "rate-limited-hop"]
    assert notes and "not a fault" in notes[0].text


def test_recorded_real_trace_rate_limited_hop_is_not_a_fault():
    v = VerdictEngine().evaluate(load_snapshot("recorded_starlink_ratelimit.json"))
    assert v.kind == KIND_HEALTHY
    assert any(e.kind == "rate-limited-hop" for e in v.evidence)


def test_outage_marks_disconnect_and_names_since():
    v = VerdictEngine().evaluate(load_snapshot("sim_dish_outage.json"))
    assert v.disconnect and v.since_ts is not None
    assert v.since_ts <= v.ts


def test_cant_tell_never_blames_a_segment():
    v = VerdictEngine().evaluate(load_snapshot("sim_cant_tell.json"))
    assert v.segment is None and v.confidence == "low"
    assert v.kind == KIND_UNKNOWN  # an unmapped disconnect is "unknown", not "still measuring"
    assert v.kind == KIND_UNKNOWN


def ok(rtt=30.0):
    return lambda i: (True, rtt)


def test_target_that_never_answers_is_cant_tell_not_an_outage():
    spec = [(1, "192.168.1.1", "gateway", False, ok(1)),
            (2, "100.64.0.1", "dish", False, ok(25)),
            (3, "1.1.1.1", "internet", True, lambda i: (False, None))]
    v = VerdictEngine().evaluate(make_trace(spec))
    assert v.kind == KIND_UNKNOWN and not v.disconnect
    assert "never answers" in v.headline


def test_silent_intermediate_hops_are_ignored_not_blamed():
    spec = [(1, "192.168.1.1", "gateway", False, ok(1)),
            (2, None, "internet", False, lambda i: (False, None)),
            (3, "1.1.1.1", "internet", True, ok(30))]
    v = VerdictEngine().evaluate(make_trace(spec))
    assert v.kind == KIND_HEALTHY


def test_middle_hop_down_but_later_hops_fine_is_not_an_outage():
    def dead_tail(i):
        return (i < 40, 20.0)
    spec = [(1, "192.168.1.1", "gateway", False, ok(1)),
            (2, "198.51.100.1", "internet", False, dead_tail),
            (3, "1.1.1.1", "internet", True, ok(30))]
    v = VerdictEngine().evaluate(make_trace(spec))
    assert v.kind == KIND_HEALTHY
    assert any(e.kind == "ignored-hop" for e in v.evidence) is False  # only noted on target outage


def test_loss_only_at_target_cant_attribute():
    spec = [(1, "192.168.1.1", "gateway", False, ok(1)),
            (2, "198.51.100.1", "internet", False, ok(20)),
            (3, "1.1.1.1", "internet", True, lambda i: (i % 3 != 0, 30.0))]
    v = VerdictEngine().evaluate(make_trace(spec))
    assert v.kind == KIND_DEGRADED and v.segment is None and v.confidence == "low"
    assert "can't tell" in v.headline.lower()


def test_loss_at_gateway_propagating_is_gateway_loss():
    pat = lambda i: (i % 3 != 0, 5.0)
    spec = [(1, "192.168.1.1", "gateway", False, pat),
            (2, "198.51.100.1", "internet", False, pat),
            (3, "1.1.1.1", "internet", True, pat)]
    v = VerdictEngine().evaluate(make_trace(spec))
    assert v.kind == KIND_DEGRADED and v.segment == SEG_GATEWAY and v.rule == "loss"


def test_no_route_is_a_pc_outage():
    snap = make_trace([(1, "192.168.1.1", "gateway", False, ok(1)), (2, "1.1.1.1", "internet", True, ok(30))])
    snap.route_ok = False
    v = VerdictEngine().evaluate(snap)
    assert v.kind == KIND_OUTAGE and v.disconnect and v.segment == "pc"


def test_probes_just_started_failing_is_pending_not_healthy():
    pat = lambda i: (i < 57, 30.0)   # last 3 fail
    spec = [(1, "192.168.1.1", "gateway", False, ok(1)), (2, "1.1.1.1", "internet", True, pat)]
    v = VerdictEngine().evaluate(make_trace(spec))
    assert v.kind == KIND_MEASURING and "just started failing" in v.headline


def test_recovered_outage_is_not_reported_as_packet_loss():
    # 12 s outage 20..32 s ago, healthy since
    pat = lambda i: (not (28 <= i < 40), 30.0)
    spec = [(1, "192.168.1.1", "gateway", False, ok(1)), (2, "1.1.1.1", "internet", True, pat)]
    v = VerdictEngine().evaluate(make_trace(spec, n=60))
    assert v.kind == KIND_HEALTHY


# ------------------------------------------------------------------------ pluggable providers / rules

class FakeDishProvider:
    """Stands in for a phase C provider: dish telemetry reports obstruction."""
    name = "fake-dish"

    def collect(self, ctx):
        return [Evidence(self.name, "dish-obstruction", "Dish reports 12% of the sky obstructed.", "warn", "dish")]


class ObstructionRefiner:
    id = "obstruction-refine"
    priority = 0
    stage = "refine"

    def evaluate(self, ctx, finding=None):
        if finding and finding.segment == "dish" and ctx.evidence_of("dish-obstruction"):
            finding.explanation += " The dish itself reports obstructions, which fits."
            finding.confidence = "high"
        return finding


class RouterWanRule:
    """Stands in for a phase B rule: router says its WAN link is down."""
    id = "router-wan"
    priority = 95
    stage = "detect"

    def evaluate(self, ctx, finding=None):
        ev = ctx.evidence_of("router-wan-down")
        if not ev:
            return None
        return Finding(self.id, KIND_OUTAGE, "Router reports its WAN link down", "The router says so.",
                       "gateway", 1, "high", self.priority, None, True)


def test_extra_provider_and_refiner_plug_in_without_engine_changes():
    eng = VerdictEngine()
    eng.add_provider(FakeDishProvider())
    eng.add_rule(ObstructionRefiner())
    v = eng.evaluate(load_snapshot("sim_dish_outage.json"))
    assert v.segment == SEG_DISH
    assert "obstructions" in v.explanation and v.confidence == "high"
    assert any(e.source == "fake-dish" for e in v.evidence)


def test_extra_detect_rule_can_outrank_builtin_rules():
    class RouterProvider:
        name = "fake-router"

        def collect(self, ctx):
            return [Evidence(self.name, "router-wan-down", "Router WAN is down.", "fail", "gateway")]

    eng = VerdictEngine()
    eng.add_provider(RouterProvider())
    eng.add_rule(RouterWanRule())
    v = eng.evaluate(load_snapshot("sim_healthy.json"))
    assert v.rule == "router-wan" and v.disconnect


def test_a_crashing_provider_does_not_break_the_verdict():
    class Bad:
        name = "bad"

        def collect(self, ctx):
            raise RuntimeError("boom")

    eng = VerdictEngine()
    eng.add_provider(Bad())
    v = eng.evaluate(load_snapshot("sim_healthy.json"))
    assert v.kind == KIND_HEALTHY
    assert any(e.kind == "provider-error" for e in v.evidence)
