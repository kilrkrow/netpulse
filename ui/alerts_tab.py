"""Alerts tab: configure alert rules and view alert log."""

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox,
    QSpinBox, QCheckBox, QDialogButtonBox, QFrame, QSplitter,
    QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QFont

from core.alerts import AlertManager, AlertRule, AlertEvent, METRICS, OPERATORS

C_BG     = '#0d1117'
C_SURF   = '#161b22'
C_BORDER = '#30363d'
C_TEXT   = '#c9d1d9'
C_MUTED  = '#8b949e'
C_BLUE   = '#58a6ff'
C_GREEN  = '#3fb950'
C_YELLOW = '#d29922'
C_RED    = '#f85149'


# ---------------------------------------------------------------------------
# Rule editor dialog
# ---------------------------------------------------------------------------
class RuleDialog(QDialog):
    def __init__(self, rule: Optional[AlertRule] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Alert Rule')
        self.setModal(True)
        self.setMinimumWidth(380)
        self._rule = rule
        self._build_ui()
        if rule:
            self._populate(rule)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText('e.g. High Latency')
        form.addRow('Rule name:', self._name_edit)

        self._metric_combo = QComboBox()
        for key, (label, unit) in METRICS.items():
            self._metric_combo.addItem(f'{label} ({unit})', key)
        form.addRow('Metric:', self._metric_combo)

        self._op_combo = QComboBox()
        for op in OPERATORS:
            self._op_combo.addItem(op)
        form.addRow('Operator:', self._op_combo)

        self._thresh_spin = QDoubleSpinBox()
        self._thresh_spin.setRange(0.0, 100000.0)
        self._thresh_spin.setValue(100.0)
        self._thresh_spin.setDecimals(1)
        self._thresh_spin.setSuffix('  (ms / %)')
        form.addRow('Threshold:', self._thresh_spin)

        self._cooldown_spin = QSpinBox()
        self._cooldown_spin.setRange(5, 3600)
        self._cooldown_spin.setValue(30)
        self._cooldown_spin.setSuffix(' s')
        form.addRow('Cooldown:', self._cooldown_spin)

        self._enabled_cb = QCheckBox('Enabled')
        self._enabled_cb.setChecked(True)
        form.addRow('', self._enabled_cb)

        lay.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _populate(self, rule: AlertRule):
        self._name_edit.setText(rule.name)
        idx = self._metric_combo.findData(rule.metric)
        if idx >= 0:
            self._metric_combo.setCurrentIndex(idx)
        op_idx = self._op_combo.findText(rule.operator)
        if op_idx >= 0:
            self._op_combo.setCurrentIndex(op_idx)
        self._thresh_spin.setValue(rule.threshold)
        self._cooldown_spin.setValue(rule.cooldown_sec)
        self._enabled_cb.setChecked(rule.enabled)

    def get_rule(self) -> AlertRule:
        if self._rule:
            r = self._rule
        else:
            r = AlertRule(name='', metric='last_rtt', operator='>', threshold=100)
        r.name = self._name_edit.text().strip() or 'Unnamed'
        r.metric = self._metric_combo.currentData()
        r.operator = self._op_combo.currentText()
        r.threshold = self._thresh_spin.value()
        r.cooldown_sec = self._cooldown_spin.value()
        r.enabled = self._enabled_cb.isChecked()
        return r


# ---------------------------------------------------------------------------
# Alerts tab
# ---------------------------------------------------------------------------
class AlertsTab(QWidget):
    def __init__(self, mgr: AlertManager, parent=None):
        super().__init__(parent)
        self._mgr = mgr
        self._build_ui()
        mgr.log_updated.connect(self._refresh_log)
        mgr.alert_triggered.connect(self._on_alert)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Rules panel ──────────────────────────────────────────────
        rules_widget = QWidget()
        rl = QVBoxLayout(rules_widget)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        rules_hdr = QHBoxLayout()
        title = QLabel('Alert Rules')
        title.setStyleSheet(f'color: {C_BLUE}; font-size: 10pt; font-weight: bold;')
        rules_hdr.addWidget(title)
        rules_hdr.addStretch()

        add_btn = QPushButton('＋ Add Rule')
        add_btn.setFixedWidth(100)
        add_btn.clicked.connect(self._add_rule)
        rules_hdr.addWidget(add_btn)

        edit_btn = QPushButton('✎ Edit')
        edit_btn.setFixedWidth(80)
        edit_btn.clicked.connect(self._edit_rule)
        rules_hdr.addWidget(edit_btn)

        del_btn = QPushButton('✕ Remove')
        del_btn.setFixedWidth(90)
        del_btn.setObjectName('stopBtn')
        del_btn.clicked.connect(self._delete_rule)
        rules_hdr.addWidget(del_btn)

        rl.addLayout(rules_hdr)

        self._rules_table = QTableWidget(0, 5)
        self._rules_table.setHorizontalHeaderLabels(
            ['Name', 'Condition', 'Threshold', 'Cooldown', 'Enabled']
        )
        self._rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._rules_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._rules_table.setColumnWidth(2, 90)
        self._rules_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._rules_table.setColumnWidth(3, 80)
        self._rules_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._rules_table.setColumnWidth(4, 70)
        self._rules_table.verticalHeader().setVisible(False)
        self._rules_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._rules_table.doubleClicked.connect(self._edit_rule)
        rl.addWidget(self._rules_table)

        splitter.addWidget(rules_widget)

        # ── Alert log ────────────────────────────────────────────────
        log_widget = QWidget()
        ll = QVBoxLayout(log_widget)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)

        log_hdr = QHBoxLayout()
        log_title = QLabel('Alert Log')
        log_title.setStyleSheet(f'color: {C_BLUE}; font-size: 10pt; font-weight: bold;')
        log_hdr.addWidget(log_title)
        log_hdr.addStretch()
        clr_btn = QPushButton('Clear')
        clr_btn.setFixedWidth(70)
        clr_btn.clicked.connect(self._clear_log)
        log_hdr.addWidget(clr_btn)
        ll.addLayout(log_hdr)

        self._log_table = QTableWidget(0, 4)
        self._log_table.setHorizontalHeaderLabels(['Time', 'Rule', 'Value', 'Message'])
        self._log_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._log_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._log_table.setColumnWidth(0, 80)
        self._log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._log_table.setColumnWidth(1, 130)
        self._log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._log_table.setColumnWidth(2, 80)
        self._log_table.verticalHeader().setVisible(False)
        self._log_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ll.addWidget(self._log_table)

        splitter.addWidget(log_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

        self._refresh_rules()

    # ------------------------------------------------------------------
    def _refresh_rules(self):
        self._rules_table.setRowCount(0)
        for rule in self._mgr.rules:
            row = self._rules_table.rowCount()
            self._rules_table.insertRow(row)
            metric_label, unit = METRICS.get(rule.metric, (rule.metric, ''))
            condition = f'{metric_label} {rule.operator}'
            threshold_str = f'{rule.threshold:.1f} {unit}'
            cooldown_str = f'{rule.cooldown_sec}s'
            enabled_str = '✓' if rule.enabled else '✗'

            items = [rule.name, condition, threshold_str, cooldown_str, enabled_str]
            for col, text in enumerate(items):
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setData(Qt.ItemDataRole.UserRole, rule.id)
                if col == 4:
                    it.setForeground(QColor(C_GREEN if rule.enabled else C_MUTED))
                self._rules_table.setItem(row, col, it)

    def _selected_rule_id(self) -> Optional[str]:
        rows = self._rules_table.selectedItems()
        if not rows:
            return None
        return rows[0].data(Qt.ItemDataRole.UserRole)

    def _add_rule(self):
        dlg = RuleDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._mgr.add_rule(dlg.get_rule())
            self._refresh_rules()

    def _edit_rule(self):
        rule_id = self._selected_rule_id()
        if not rule_id:
            return
        rule = self._mgr.get_rule(rule_id)
        if not rule:
            return
        dlg = RuleDialog(rule=rule, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.get_rule()  # mutates rule in place
            self._refresh_rules()

    def _delete_rule(self):
        rule_id = self._selected_rule_id()
        if rule_id:
            self._mgr.remove_rule(rule_id)
            self._refresh_rules()

    # ------------------------------------------------------------------
    @Slot()
    def _refresh_log(self):
        self._log_table.setRowCount(0)
        for event in reversed(self._mgr.log[-200:]):
            row = self._log_table.rowCount()
            self._log_table.insertRow(row)
            ts = event.timestamp.strftime('%H:%M:%S')
            metric_label, unit = METRICS.get(event.metric, (event.metric, ''))
            val_str = f'{event.value:.1f} {unit}'
            items = [ts, event.rule_name, val_str, event.message]
            for col, text in enumerate(items):
                it = QTableWidgetItem(text)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col != 3 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                it.setForeground(QColor(C_RED))
                self._log_table.setItem(row, col, it)

    @Slot(object)
    def _on_alert(self, event: AlertEvent):
        self._refresh_log()

    def _clear_log(self):
        self._mgr.log.clear()
        self._log_table.setRowCount(0)
