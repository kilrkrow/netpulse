"""Settings for the root-cause view: target, probe interval, label overrides, lookups, notifications."""

from __future__ import annotations

import ipaddress

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from core.rc.model import SEG_DISH, SEG_GATEWAY, SEG_INTERNET, SEGMENT_NAMES
from ui.rc import theme


class SettingsDialog(QDialog):
    def __init__(self, settings_store, on_applied=None, parent=None):
        super().__init__(parent)
        self.store = settings_store
        self.on_applied = on_applied
        self.setWindowTitle("NetPulse Settings")
        self.setMinimumWidth(480)
        s = settings_store.value
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.target = QLineEdit(s.target)
        self.target.setPlaceholderText("1.1.1.1")
        form.addRow("Probe target", self.target)
        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.5, 10.0)
        self.interval.setSingleStep(0.5)
        self.interval.setSuffix(" s")
        self.interval.setValue(s.interval_s)
        form.addRow("Probe interval", self.interval)
        self.dish = QLineEdit(s.dish_lan_ip)
        form.addRow("Dish address on the LAN", self.dish)
        self.notify = QCheckBox("Show a notification when an outage starts or ends")
        self.notify.setChecked(s.notifications)
        form.addRow("", self.notify)
        self.lookups = QCheckBox("Allow IP lookups (sends public addresses to Team Cymru, RDAP and DNS)")
        self.lookups.setChecked(s.lookups_allowed)
        form.addRow("", self.lookups)
        self.autoid = QCheckBox("Identify hops by owner so the Starlink dish can be recognized")
        self.autoid.setChecked(s.auto_identify_hops)
        form.addRow("", self.autoid)
        lay.addLayout(form)

        lay.addWidget(QLabel("YOUR HOP LABELS"))
        self.overrides = QComboBox()
        self._fill_overrides()
        lay.addWidget(self.overrides)
        self.remove_btn = QPushButton("Remove selected label")
        self.remove_btn.clicked.connect(self._remove_override)
        lay.addWidget(self.remove_btn)
        hint = QLabel("Right-click a hop in the path to label it as Gateway, Dish or Internet.")
        hint.setStyleSheet(f"color: {theme.DIM};")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _fill_overrides(self) -> None:
        self.overrides.clear()
        ov = self.store.value.label_overrides
        if not ov:
            self.overrides.addItem("(none set)", None)
            return
        for k, seg in sorted(ov.items()):
            self.overrides.addItem(f"{k.split(':', 1)[1]}  ->  {SEGMENT_NAMES.get(seg, seg).title()}", k)

    def _remove_override(self) -> None:
        k = self.overrides.currentData()
        if k:
            self.store.set_override(k, "")
            self._fill_overrides()

    def _save(self) -> None:
        target = self.target.text().strip() or "1.1.1.1"
        try:
            ipaddress.ip_address(target)
        except ValueError:
            QMessageBox.warning(self, "Settings", "The probe target must be an IP address, for example 1.1.1.1 or 8.8.8.8.")
            return
        dish = self.dish.text().strip() or "192.168.100.1"
        try:
            ipaddress.ip_address(dish)
        except ValueError:
            QMessageBox.warning(self, "Settings", "The dish address must be an IP address.")
            return
        s = self.store.value
        s.target, s.interval_s, s.dish_lan_ip = target, float(self.interval.value()), dish
        s.notifications = self.notify.isChecked()
        s.lookups_allowed = self.lookups.isChecked()
        if s.lookups_allowed:
            s.lookups_notice_seen = True
        s.auto_identify_hops = self.autoid.isChecked()
        self.store.save()
        if self.on_applied:
            self.on_applied()
        self.accept()
