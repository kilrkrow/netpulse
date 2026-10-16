"""Probe engine (with the simulated prober), hop labeling and discovery behaviour."""

import time

from core.rc.ipclass import classify_ip, lookup_allowed, skip_reason
from core.rc.labeler import label_hop, override_key_ip, override_key_ttl
from core.rc.model import SEG_DISH, SEG_GATEWAY, SEG_INTERNET, SEG_PC, Sample, compute_stats
from core.rc.netinfo import RouteInfo
from core.rc.probe import ProbeConfig, ProbeEngine
from core.rc.sim import SCENARIOS, SIM_GATEWAY, SIM_SOURCE, SIM_TARGET, Effect, Scenario, SimClock, SimProber, sim_route


def make_engine(scenario, history=0, route_fn=sim_route, cfg=None):
    now = 1_800_000_000.0
    clock = SimClock(now - history)
    eng = ProbeEngine(SimProber(scenario, clock, now), cfg or ProbeConfig(target=SIM_TARGET, dish_lan_ip="192.168.100.1"),
                      clock=clock.time, route_fn=route_fn)
    return eng, clock


def run(eng, clock, seconds):
    for _ in range(seconds):
        eng.run_once()
        clock.advance(1.0)


def test_discovery_maps_the_simulated_path_and_labels_it():
    eng, clock = make_engine(SCENARIOS["healthy"], history=30)
    run(eng, clock, 12)
    snap = eng.snapshot()
    assert snap.mapped and snap.route_ok
    segs = [(h.ttl, h.segment) for h in snap.hops]
    assert segs[0] == (0, SEG_PC)
    assert segs[1] == (1, SEG_GATEWAY)
    assert segs[2] == (2, SEG_DISH)                 # 100.64.0.1 is CGNAT
    assert all(s == SEG_INTERNET for _, s in segs[3:])
    assert snap.hops[-1].is_target and snap.hops[-1].ip == SIM_TARGET
    assert all(len(h.samples) >= 10 for h in snap.hops if h.ttl >= 1)
    assert "dish-lan" in snap.side_probes


def test_every_hop_gets_latency_loss_and_jitter():
    eng, clock = make_engine(SCENARIOS["loss"], history=60)
    run(eng, clock, 60)
    snap = eng.snapshot()
    st = snap.hop_by_ttl(3).stats()
    assert st.sent == 60 and 0 < st.loss_pct < 100
    assert st.avg_rtt and st.jitter is not None and st.min_rtt <= st.avg_rtt <= st.max_rtt
    assert snap.hop_by_ttl(1).stats().loss_pct == 0.0


def test_known_path_survives_an_outage_and_rediscovery():
    sc = Scenario("t", "t", [Effect("down", 3, 20, 1e9)])
    eng, clock = make_engine(sc, history=0)
    run(eng, clock, 25)                 # healthy 0..20 then outage
    n_hops = len(eng.snapshot().hops)
    eng._last_discovery = -1e9          # force a due rediscovery during the outage
    run(eng, clock, 10)
    snap = eng.snapshot()
    assert len(snap.hops) == n_hops and snap.mapped
    assert snap.hops[-1].is_target


def test_route_change_restarts_discovery():
    routes = [RouteInfo(True, SIM_GATEWAY, SIM_SOURCE, 1)]
    eng, clock = make_engine(SCENARIOS["healthy"], history=0, route_fn=lambda d: routes[0])
    eng.cfg.route_check_s = 0
    run(eng, clock, 6)
    first = eng.snapshot().hops[1].samples
    assert len(first) >= 5
    routes[0] = RouteInfo(True, "192.168.1.254", SIM_SOURCE, 1)
    eng.run_once()
    assert len(eng.snapshot().hops[1].samples) <= 2          # state was reset for the new network


def test_no_route_is_reported_not_crashed():
    eng, clock = make_engine(SCENARIOS["healthy"], route_fn=lambda d: RouteInfo(False, error="x"))
    eng.run_once()
    assert eng.snapshot().route_ok is False


def test_unresponsive_everything_still_gets_a_gateway_and_target_hop():
    sc = Scenario("dead", "dead", [Effect("down", 1, -1e6, 1e9)])
    eng, clock = make_engine(sc)
    run(eng, clock, 6)
    snap = eng.snapshot()
    ttls = [h.ttl for h in snap.hops]
    assert ttls == [0, 1, 2]
    assert snap.hops[1].segment == SEG_GATEWAY and snap.hops[2].is_target and not snap.mapped


# ----------------------------------------------------------------------------- labeler

def test_label_rules():
    gw = "192.168.1.1"
    assert label_hop(0, "192.168.1.50", gw)[0] == SEG_PC
    assert label_hop(1, gw, gw)[0] == SEG_GATEWAY
    assert label_hop(2, "100.64.0.1", gw)[0] == SEG_DISH                    # CGNAT
    assert label_hop(2, "100.127.255.254", gw)[0] == SEG_DISH               # top of 100.64.0.0/10
    assert label_hop(2, "100.128.0.1", gw)[0] == SEG_INTERNET               # just outside it
    assert label_hop(2, "192.168.100.1", gw)[0] == SEG_DISH                 # the dish itself
    assert label_hop(4, "198.51.100.9", gw)[0] == SEG_INTERNET
    assert label_hop(4, "198.51.100.9", gw, asn=14593)[0] == SEG_DISH       # Starlink ASN
    assert label_hop(4, "198.51.100.9", gw, asn=15169)[0] == SEG_INTERNET
    assert label_hop(2, "10.1.2.3", gw, prev_segment=SEG_GATEWAY)[0] == SEG_GATEWAY   # more LAN
    assert label_hop(3, "10.1.2.3", gw, prev_segment=SEG_DISH)[0] == SEG_DISH         # Starlink-internal


def test_user_overrides_win_and_are_by_ip_or_hop_number():
    gw = "192.168.1.1"
    ov = {override_key_ip("198.51.100.9"): SEG_DISH, override_key_ttl(5): SEG_GATEWAY}
    assert label_hop(4, "198.51.100.9", gw, ov) == (SEG_DISH, "override")
    assert label_hop(5, "203.0.113.4", gw, ov) == (SEG_GATEWAY, "override")
    assert label_hop(1, gw, gw, {override_key_ip(gw): SEG_INTERNET}) == (SEG_INTERNET, "override")


def test_engine_applies_overrides_and_asn():
    sc = SCENARIOS["healthy"]
    now = 1_800_000_000.0
    clock = SimClock(now - 20)
    ov = {override_key_ip("198.51.100.1"): SEG_DISH}
    eng = ProbeEngine(SimProber(sc, clock, now), ProbeConfig(target=SIM_TARGET), clock=clock.time, route_fn=sim_route,
                      overrides_fn=lambda: ov, asn_fn=lambda ip: 14593 if ip == "198.51.100.17" else None)
    run(eng, clock, 10)
    snap = eng.snapshot()
    assert snap.hop_by_ttl(3).segment == SEG_DISH and snap.hop_by_ttl(3).label_source == "override"
    assert snap.hop_by_ttl(4).segment == SEG_DISH and snap.hop_by_ttl(4).label_source == "auto"
    assert snap.hop_by_ttl(5).segment == SEG_INTERNET


# ----------------------------------------------------------------------------- stats / ip classes

def test_compute_stats_loss_jitter_runs():
    s = [Sample(i, ok, r) for i, (ok, r) in enumerate([(True, 10.0), (True, 14.0), (False, None), (False, None), (False, None)])]
    st = compute_stats(s)
    assert st.sent == 5 and st.recv == 2 and round(st.loss_pct) == 60
    assert st.consec_fail == 3 and st.first_fail_ts == 2 and st.last_ok_ts == 1
    assert st.jitter == 4.0 and st.avg_rtt == 12.0


def test_ip_classification_never_allows_non_public():
    for ip in ["10.1.1.1", "172.16.0.9", "192.168.1.1", "100.64.0.1", "100.100.1.1", "169.254.1.1", "127.0.0.1",
               "224.0.0.1", "192.0.2.5", "198.51.100.5", "203.0.113.5", "0.0.0.0", "255.255.255.255", "240.0.0.1",
               "198.18.0.1", "::1", "fe80::1", "2001:db8::1", "fc00::1", "not-an-ip"]:
        assert not lookup_allowed(ip), ip
        assert skip_reason(ip) and "Not looked up" in skip_reason(ip)
    for ip in ["1.1.1.1", "8.8.8.8", "2606:4700:4700::1111"]:
        assert lookup_allowed(ip) and skip_reason(ip) is None
    assert classify_ip("100.64.0.1") == "cgnat"
