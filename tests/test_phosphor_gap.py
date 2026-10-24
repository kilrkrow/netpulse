"""The phosphor trace joins samples across a gap that scales with the probe interval."""

import sys

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.rc.model import (SEG_INTERNET, SEG_PC, HopView, PathSnapshot, Sample, Verdict)  # noqa: E402
from core.rc.settings import SettingsStore  # noqa: E402
from ui.rc.page import PathPage  # noqa: E402
from ui.rc.widgets import trace_break_gap  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication(sys.argv[:1])


def test_break_gap_scales_with_interval():
    assert trace_break_gap(1.0) == 4.5          # the old fixed cutoff, at the default interval
    assert trace_break_gap(5.0) == 22.5         # a 5 s probe still draws a line
    assert trace_break_gap(0.5) == 2.25
    assert trace_break_gap(0) == 4.5            # a bad interval falls back to 1 s
    assert trace_break_gap(-3) == 4.5
    assert trace_break_gap(float("nan")) == 4.5


class _Cfg:
    def __init__(self, interval_s):
        self.interval_s = interval_s


class _Ctl:
    def __init__(self, interval_s):
        self.engine = type("E", (), {})()
        self.engine.cfg = _Cfg(interval_s)
        self.verdict = None


def _snap(now):
    samples = [Sample(now - 25 + i * 5, True, 12.0) for i in range(6)]
    hops = [
        HopView(ttl=0, ip="192.168.1.50", segment=SEG_PC, label_source="fixed", ever_ok=True),
        HopView(ttl=1, ip="1.1.1.1", segment=SEG_INTERNET, is_target=True, samples=samples,
                ever_ok=True, total_sent=len(samples)),
    ]
    return PathSnapshot(ts=now, target="1.1.1.1", hops=hops, gateway_ip="192.168.1.1",
                        source_ip="192.168.1.50", mapped=True, started_ts=now - 25)


def _verdict(now):
    return Verdict(kind="healthy", headline="Network is healthy", explanation="", segment=None, ttl=None,
                   confidence="high", rule="ok", evidence=[], ts=now)


def test_path_traces_follow_the_live_interval(app, tmp_path):
    now = 1_800_000_000.0
    ctl = _Ctl(5.0)
    page = PathPage(ctl, SettingsStore(str(tmp_path / "settings.json")))
    verdict = _verdict(now)
    ctl.verdict = verdict
    page.update_data(_snap(now), verdict)

    spark = page.path._cells[1].spark
    assert spark.interval_s == 5.0
    assert page.detail.graph.interval_s == 5.0
    assert trace_break_gap(spark.interval_s) > 5.0      # consecutive 5 s samples join

    ctl.engine.cfg.interval_s = 1.0
    page.redraw()
    assert spark.interval_s == 1.0
    assert page.detail.graph.interval_s == 1.0
    assert trace_break_gap(spark.interval_s) == 4.5
