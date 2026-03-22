"""Monitor tab: real-time RTT graph + comprehensive stats grid."""

import datetime
import time
from collections import deque
from typing import Deque, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSplitter, QVBoxLayout, QWidget

from core.alerts import AlertManager
from core.ping_engine import PingEngine, PingResult, PingStats

C_BG = "#0d1117"
C_SURFACE = "#161b22"
C_BORDER = "#30363d"
C_TEXT = "#c9d1d9"
C_MUTED = "#8b949e"
C_GREEN = "#3fb950"
C_YELLOW = "#d29922"
C_RED = "#f85149"
C_BLUE = "#58a6ff"


def _rtt_color(rtt: float, threshold: float) -> str:
    if rtt > threshold:
        return C_RED
    if rtt > threshold * 0.75:
        return C_YELLOW
    return C_GREEN


class StatBox(QFrame):
    """A small card showing a label and a large value."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statBox")
        self.setStyleSheet(
            f"""
            QFrame#statBox {{
                background: {C_SURFACE};
                border: 1px solid {C_BORDER};
                border-radius: 5px;
            }}
            """
        )
        self.setMinimumWidth(110)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(1)

        self._lbl = QLabel(label.upper())
        self._lbl.setStyleSheet(
            f"color: {C_MUTED}; font-size: 8pt; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._val = QLabel("-")
        self._val.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self._val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val.setStyleSheet(f"color: {C_TEXT}; background: transparent; border: none;")

        layout.addWidget(self._lbl)
        layout.addWidget(self._val)

    def set_value(self, text: str, color: str = C_TEXT):
        self._val.setText(text)
        self._val.setStyleSheet(
            f"color: {color}; font-size: 14pt; font-weight: bold; "
            "background: transparent; border: none;"
        )


class MonitorTab(QWidget):
    def __init__(self, alert_mgr: AlertManager, parent=None):
        super().__init__(parent)
        self._alert_mgr = alert_mgr
        self._engine: Optional[PingEngine] = None
        self._graph_window = 300
        self._times: Deque[float] = deque(maxlen=3600)
        self._rtts: Deque[Optional[float]] = deque(maxlen=3600)
        self._start_ts = time.time()
        self._last_stats: Optional[PingStats] = None
        self._user_zoomed: bool = False

        self._build_ui()

        self._graph_timer = QTimer()
        self._graph_timer.timeout.connect(self._refresh_graph)
        self._graph_timer.start(250)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(2)

        graph_panel = QWidget()
        graph_layout = QVBoxLayout(graph_panel)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(2)

        self._rtt_plot = self._build_rtt_plot()
        self._loss_plot = self._build_loss_plot()

        graph_layout.addWidget(self._rtt_plot, 4)

        zoom_bar = QHBoxLayout()
        zoom_bar.setContentsMargins(0, 1, 2, 0)
        zoom_bar.addStretch()
        self._reset_zoom_btn = QPushButton("● Live")
        self._reset_zoom_btn.setFixedWidth(90)
        self._reset_zoom_btn.setToolTip("Click to return to live auto-scrolling view")
        self._reset_zoom_btn.setStyleSheet(
            "font-size: 8pt; padding: 2px 6px; color: #3fb950;"
        )
        self._reset_zoom_btn.clicked.connect(self._reset_zoom)
        zoom_bar.addWidget(self._reset_zoom_btn)
        graph_layout.addLayout(zoom_bar)

        graph_layout.addWidget(self._loss_plot, 1)
        splitter.addWidget(graph_panel)
        splitter.addWidget(self._build_stats_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

    def _build_rtt_plot(self) -> pg.PlotWidget:
        axis = pg.DateAxisItem(orientation="bottom")
        plot = pg.PlotWidget(axisItems={"bottom": axis})
        plot.setBackground(C_BG)
        plot.getAxis("left").setTextPen(C_MUTED)
        plot.getAxis("bottom").setTextPen(C_MUTED)
        plot.getAxis("left").setPen(C_BORDER)
        plot.getAxis("bottom").setPen(C_BORDER)
        plot.setLabel("left", "RTT (ms)", color=C_MUTED)
        plot.showGrid(x=True, y=True, alpha=0.15)
        plot.setMouseEnabled(x=True, y=True)
        plot.setMinimumHeight(200)

        self._rtt_line = plot.plot([], [], pen=pg.mkPen(C_GREEN, width=1.5))
        self._rtt_scatter = pg.ScatterPlotItem(size=5, pen=pg.mkPen(None))
        plot.addItem(self._rtt_scatter)

        self._lost_scatter = pg.ScatterPlotItem(
            symbol="x",
            size=9,
            pen=pg.mkPen(C_RED, width=2),
            brush=pg.mkBrush(None),
        )
        plot.addItem(self._lost_scatter)

        self._avg_line = pg.InfiniteLine(
            angle=0,
            movable=False,
            pen=pg.mkPen(C_BLUE, width=1.2, style=Qt.PenStyle.DashLine),
        )
        plot.addItem(self._avg_line)

        self._thresh_line = pg.InfiniteLine(
            angle=0,
            movable=False,
            pen=pg.mkPen(C_RED, width=1.2, style=Qt.PenStyle.DotLine),
        )
        plot.addItem(self._thresh_line)

        self._avg_label = pg.TextItem(text="", color=C_BLUE, anchor=(1, 0))
        self._thresh_label = pg.TextItem(text="", color=C_RED, anchor=(1, 1))
        plot.addItem(self._avg_label)
        plot.addItem(self._thresh_label)
        plot.getViewBox().sigRangeChangedManually.connect(self._on_user_zoom)
        return plot

    def _build_loss_plot(self) -> pg.PlotWidget:
        plot = pg.PlotWidget()
        plot.setBackground(C_BG)
        plot.getAxis("left").setTextPen(C_MUTED)
        plot.getAxis("bottom").setTextPen(C_MUTED)
        plot.getAxis("left").setPen(C_BORDER)
        plot.getAxis("bottom").setPen(C_BORDER)
        plot.setLabel("left", "Loss %", color=C_MUTED)
        plot.showGrid(x=False, y=True, alpha=0.15)
        plot.setMaximumHeight(80)
        plot.setMouseEnabled(x=False, y=False)
        plot.setYRange(0, 100, padding=0)
        plot.getAxis("bottom").setStyle(showValues=False)

        self._loss_curve = plot.plot(
            [],
            [],
            pen=pg.mkPen(C_RED, width=1),
            fillLevel=0,
            brush=pg.mkBrush(QColor(248, 81, 73, 60)),
        )
        return plot

    def _build_stats_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {C_BG};")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        grid = QGridLayout()
        grid.setSpacing(5)
        defs = [
            ("last_rtt", "Last RTT", 0, 0),
            ("rtt_avg", "Avg RTT", 0, 1),
            ("rtt_min", "Min RTT", 0, 2),
            ("rtt_max", "Max RTT", 0, 3),
            ("jitter", "Jitter", 0, 4),
            ("rtt_stddev", "Std Dev", 0, 5),
            ("loss_pct", "Pkt Loss", 1, 0),
            ("last_ttl", "TTL", 1, 1),
            ("samples", "Samples", 1, 2),
            ("received", "Received", 1, 3),
            ("lost", "Lost", 1, 4),
            ("_uptime", "Uptime", 1, 5),
        ]

        self._stat_boxes: dict[str, StatBox] = {}
        for key, label, row, col in defs:
            box = StatBox(label)
            self._stat_boxes[key] = box
            grid.addWidget(box, row, col)

        outer.addLayout(grid)
        return panel

    def _on_user_zoom(self, axes):
        if not self._user_zoomed:
            self._user_zoomed = True
            self._reset_zoom_btn.setText("↺ Live View")
            self._reset_zoom_btn.setStyleSheet(
                "font-size: 8pt; padding: 2px 6px; "
                "background-color: #1a4731; border-color: #2ea043; color: #3fb950; font-weight: bold;"
            )
            self._reset_zoom_btn.setToolTip("Zoom is active — click to return to live auto-scrolling view")

    def _reset_zoom(self):
        self._user_zoomed = False
        self._rtt_plot.enableAutoRange()
        self._reset_zoom_btn.setText("● Live")
        self._reset_zoom_btn.setStyleSheet(
            "font-size: 8pt; padding: 2px 6px; color: #3fb950;"
        )
        self._reset_zoom_btn.setToolTip("Click to return to live auto-scrolling view")

    def set_engine(self, engine: PingEngine, graph_window: int):
        if self._engine:
            try:
                self._engine.result_ready.disconnect(self._on_result)
                self._engine.stats_updated.disconnect(self._on_stats)
            except Exception:
                pass

        self._engine = engine
        self._graph_window = graph_window
        self._times.clear()
        self._rtts.clear()
        self._start_ts = time.time()
        self._last_stats = None
        self._user_zoomed = False
        self._reset_zoom_btn.setText("● Live")
        self._reset_zoom_btn.setStyleSheet(
            "font-size: 8pt; padding: 2px 6px; color: #3fb950;"
        )
        self._engine.result_ready.connect(self._on_result)
        self._engine.stats_updated.connect(self._on_stats)
        self._rtt_plot.enableAutoRange()
        self._loss_plot.enableAutoRange()

    @Slot(object)
    def _on_result(self, result: PingResult):
        self._times.append(result.timestamp.timestamp())
        self._rtts.append(result.rtt_ms)

    @Slot(object)
    def _on_stats(self, stats: PingStats):
        self._last_stats = stats
        self._update_stat_boxes(stats)

    def _refresh_graph(self):
        if not self._times:
            return

        times = list(self._times)[-self._graph_window :]
        rtts = list(self._rtts)[-self._graph_window :]

        self._rtt_line.setData(
            x=np.array(times, dtype=float),
            y=np.array([value if value is not None else np.nan for value in rtts], dtype=float),
        )

        threshold = self._get_rtt_threshold()
        valid_values = [value for value in rtts if value is not None]

        if not self._user_zoomed:
            if len(times) >= 2:
                self._rtt_plot.setXRange(times[0], times[-1], padding=0.02)
            if valid_values:
                self._rtt_plot.setYRange(
                    0,
                    max(max(valid_values) * 1.25, threshold * 1.15, 10.0),
                    padding=0,
                )

        spots = []
        for timestamp, rtt in zip(times, rtts):
            if rtt is not None:
                spots.append(
                    {
                        "pos": (timestamp, rtt),
                        "brush": pg.mkBrush(QColor(_rtt_color(rtt, threshold))),
                        "size": 5,
                    }
                )
        self._rtt_scatter.setData(spots)

        lost_timestamps = [timestamp for timestamp, rtt in zip(times, rtts) if rtt is None]
        if lost_timestamps:
            self._lost_scatter.setData(x=lost_timestamps, y=[2.0] * len(lost_timestamps))
        else:
            self._lost_scatter.setData([], [])

        if self._last_stats and self._last_stats.rtt_avg is not None and times:
            avg = self._last_stats.rtt_avg
            self._avg_line.setValue(avg)
            self._avg_label.setText(f"avg {avg:.1f} ms")
            self._avg_label.setPos(times[-1], avg)

        if times:
            self._thresh_line.setValue(threshold)
            self._thresh_label.setText(f"alert >{threshold:.0f} ms")
            self._thresh_label.setPos(times[-1], threshold)

        self._refresh_loss_chart(times, rtts)

    def _refresh_loss_chart(self, times, rtts):
        bucket = 10
        if len(rtts) < bucket:
            self._loss_curve.setData([], [])
            return

        xs, ys = [], []
        for index in range(bucket, len(rtts) + 1, bucket):
            chunk = rtts[index - bucket : index]
            lost = sum(1 for value in chunk if value is None)
            xs.append(times[index - 1])
            ys.append(lost / bucket * 100)

        self._loss_curve.setData(x=np.array(xs, dtype=float), y=np.array(ys, dtype=float))
        if xs and len(times) >= 2:
            self._loss_plot.setXRange(times[0], times[-1], padding=0.02)

    def _get_rtt_threshold(self) -> float:
        for rule in self._alert_mgr.rules:
            if rule.metric == "last_rtt" and rule.operator in (">", ">=") and rule.enabled:
                return rule.threshold
        return 100.0

    def _update_stat_boxes(self, stats: PingStats):
        threshold = self._get_rtt_threshold()

        def ms(value):
            return f"{value:.1f} ms" if value is not None else "-"

        def colored_rtt(value):
            if value is None:
                return "-", C_MUTED
            return f"{value:.1f} ms", _rtt_color(value, threshold)

        value, color = colored_rtt(stats.last_rtt)
        self._stat_boxes["last_rtt"].set_value(value, color)
        self._stat_boxes["rtt_avg"].set_value(ms(stats.rtt_avg))
        self._stat_boxes["rtt_min"].set_value(ms(stats.rtt_min))
        self._stat_boxes["rtt_max"].set_value(ms(stats.rtt_max))
        self._stat_boxes["jitter"].set_value(ms(stats.jitter))
        self._stat_boxes["rtt_stddev"].set_value(ms(stats.rtt_stddev))

        loss_color = C_GREEN if stats.loss_pct == 0 else (C_YELLOW if stats.loss_pct < 5 else C_RED)
        self._stat_boxes["loss_pct"].set_value(f"{stats.loss_pct:.1f}%", loss_color)
        self._stat_boxes["last_ttl"].set_value(str(stats.last_ttl) if stats.last_ttl else "-")
        self._stat_boxes["samples"].set_value(str(stats.samples))
        self._stat_boxes["received"].set_value(str(stats.received), C_GREEN if stats.received else C_MUTED)
        self._stat_boxes["lost"].set_value(str(stats.lost), C_RED if stats.lost else C_TEXT)

        if stats.session_start:
            elapsed = datetime.datetime.now() - stats.session_start
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            self._stat_boxes["_uptime"].set_value(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
