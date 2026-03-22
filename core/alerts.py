"""Alert rules and notification manager."""

import uuid
import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Callable

from PySide6.QtCore import QObject, Signal


METRICS = {
    'last_rtt':   ('Last RTT',    'ms'),
    'rtt_avg':    ('Avg RTT',     'ms'),
    'rtt_min':    ('Min RTT',     'ms'),
    'rtt_max':    ('Max RTT',     'ms'),
    'jitter':     ('Jitter',      'ms'),
    'rtt_stddev': ('Std Dev',     'ms'),
    'loss_pct':   ('Packet Loss', '%'),
}

OPERATORS = ['>', '>=', '<', '<=', '==']


@dataclass
class AlertRule:
    name: str
    metric: str          # key from METRICS
    operator: str        # one of OPERATORS
    threshold: float
    enabled: bool = True
    cooldown_sec: int = 30
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    last_triggered: Optional[datetime.datetime] = None


@dataclass
class AlertEvent:
    timestamp: datetime.datetime
    rule_name: str
    metric: str
    value: float
    threshold: float
    operator: str
    message: str


def _evaluate(value: float, op: str, threshold: float) -> bool:
    if op == '>':   return value > threshold
    if op == '>=':  return value >= threshold
    if op == '<':   return value < threshold
    if op == '<=':  return value <= threshold
    if op == '==':  return abs(value - threshold) < 0.001
    return False


class AlertManager(QObject):
    """Checks PingStats against rules and fires notifications."""

    alert_triggered = Signal(object)   # AlertEvent
    log_updated = Signal()

    def __init__(self):
        super().__init__()
        self.rules: List[AlertRule] = self._default_rules()
        self.log: List[AlertEvent] = []
        self._notify_callback: Optional[Callable[[str, str], None]] = None

    def set_notify_callback(self, cb: Callable[[str, str], None]):
        """cb(title, message) — e.g., show a system tray balloon."""
        self._notify_callback = cb

    def check(self, stats) -> List[AlertEvent]:
        """Called on every PingStats update. Returns any new alerts."""
        now = datetime.datetime.now()
        fired: List[AlertEvent] = []

        for rule in self.rules:
            if not rule.enabled:
                continue
            value = getattr(stats, rule.metric, None)
            if value is None:
                continue

            if not _evaluate(value, rule.operator, rule.threshold):
                continue

            # Cooldown check
            if rule.last_triggered:
                elapsed = (now - rule.last_triggered).total_seconds()
                if elapsed < rule.cooldown_sec:
                    continue

            rule.last_triggered = now
            metric_label, unit = METRICS.get(rule.metric, (rule.metric, ''))
            msg = (
                f"{rule.name}: {metric_label} = {value:.1f}{unit} "
                f"{rule.operator} {rule.threshold:.1f}{unit}"
            )
            event = AlertEvent(
                timestamp=now,
                rule_name=rule.name,
                metric=rule.metric,
                value=value,
                threshold=rule.threshold,
                operator=rule.operator,
                message=msg,
            )
            self.log.append(event)
            fired.append(event)
            self.alert_triggered.emit(event)
            self.log_updated.emit()

            if self._notify_callback:
                self._notify_callback('NetPulse Alert', msg)

        return fired

    def add_rule(self, rule: AlertRule):
        self.rules.append(rule)

    def remove_rule(self, rule_id: str):
        self.rules = [r for r in self.rules if r.id != rule_id]

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        for r in self.rules:
            if r.id == rule_id:
                return r
        return None

    def _default_rules(self) -> List[AlertRule]:
        return [
            AlertRule('High Latency', 'last_rtt', '>', 100, enabled=True, cooldown_sec=30),
            AlertRule('High Loss',    'loss_pct', '>', 5.0, enabled=True, cooldown_sec=60),
            AlertRule('High Jitter',  'jitter',   '>', 20,  enabled=True, cooldown_sec=60),
        ]
