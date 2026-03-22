"""Domain Dossier tab: DNS records, GeoIP, WHOIS."""

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from core.dossier import DossierEngine, GeoInfo, WhoisInfo

C_SURF = "#161b22"
C_BORDER = "#30363d"
C_TEXT = "#c9d1d9"
C_MUTED = "#8b949e"
C_BLUE = "#58a6ff"
C_GREEN = "#3fb950"


def _section(title: str) -> QLabel:
    label = QLabel(title)
    label.setStyleSheet(
        f"color: {C_BLUE}; font-size: 10pt; font-weight: bold; "
        f"border-bottom: 1px solid {C_BORDER}; padding-bottom: 3px;"
    )
    return label


def _kv(key: str, value: str) -> tuple[QLabel, QLabel]:
    key_label = QLabel(key + ":")
    key_label.setStyleSheet(f"color: {C_MUTED}; font-size: 9pt;")
    value_label = QLabel(value)
    value_label.setStyleSheet(f"color: {C_TEXT}; font-size: 9pt;")
    value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    value_label.setWordWrap(True)
    return key_label, value_label


class InfoGrid(QFrame):
    """A key-value grid for structured info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: {C_SURF}; border: 1px solid {C_BORDER}; "
            f"border-radius: 5px; }}"
        )
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(4)
        self._row = 0
        self._labels: dict[str, QLabel] = {}

    def add_row(self, key: str, value: str = "-"):
        key_label, value_label = _kv(key, value)
        self._layout.addWidget(key_label, self._row, 0, Qt.AlignmentFlag.AlignTop)
        self._layout.addWidget(value_label, self._row, 1, Qt.AlignmentFlag.AlignTop)
        self._labels[key] = value_label
        self._row += 1

    def set_value(self, key: str, value: str):
        if key in self._labels:
            self._labels[key].setText(value or "-")

    def clear_values(self):
        for label in self._labels.values():
            label.setText("-")


class DossierTab(QWidget):
    def __init__(self, engine: DossierEngine, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._target = ""
        self._active_request_id: int | None = None
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Lookup:"))
        self._lookup_combo = QComboBox()
        self._lookup_combo.setEditable(True)
        self._lookup_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._lookup_combo.lineEdit().setPlaceholderText("domain or IP (e.g. example.com)")
        self._lookup_combo.lineEdit().returnPressed.connect(self._lookup)
        bar.addWidget(self._lookup_combo)

        self._lookup_btn = QPushButton("Lookup")
        self._lookup_btn.setFixedWidth(110)
        self._lookup_btn.clicked.connect(self._lookup)
        bar.addWidget(self._lookup_btn)
        root.addLayout(bar)

        self._status_lbl = QLabel("Enter a domain or IP and click Lookup.")
        self._status_lbl.setStyleSheet(f"color: {C_MUTED}; font-size: 9pt;")
        root.addWidget(self._status_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        root.addWidget(scroll)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        content_layout.addWidget(_section("Resolution"))
        self._res_grid = InfoGrid()
        self._res_grid.add_row("Target")
        self._res_grid.add_row("Resolved IP")
        self._res_grid.add_row("Reverse DNS")
        content_layout.addWidget(self._res_grid)

        content_layout.addWidget(_section("DNS Records"))
        self._dns_table = QTableWidget(0, 3)
        self._dns_table.setHorizontalHeaderLabels(["Type", "TTL", "Value"])
        self._dns_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._dns_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._dns_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._dns_table.setColumnWidth(0, 60)
        self._dns_table.setColumnWidth(1, 70)
        self._dns_table.verticalHeader().setVisible(False)
        self._dns_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._dns_table.setMaximumHeight(200)
        content_layout.addWidget(self._dns_table)

        content_layout.addWidget(_section("GeoIP"))
        self._geo_grid = InfoGrid()
        for key in ("Country", "Region", "City", "Timezone", "ISP", "Organisation", "ASN", "Coordinates"):
            self._geo_grid.add_row(key)
        content_layout.addWidget(self._geo_grid)

        content_layout.addWidget(_section("WHOIS"))
        self._whois_grid = InfoGrid()
        for key in (
            "Domain",
            "Registrar",
            "Created",
            "Expires",
            "Updated",
            "Name Servers",
            "Status",
            "Registrant",
            "Org",
            "Country",
            "Emails",
        ):
            self._whois_grid.add_row(key)
        content_layout.addWidget(self._whois_grid)
        content_layout.addStretch()

    def _connect_signals(self):
        self._engine.ip_resolved.connect(self._on_ip_resolved)
        self._engine.reverse_dns_ready.connect(self._on_rdns)
        self._engine.dns_records_ready.connect(self._on_dns)
        self._engine.geo_ready.connect(self._on_geo)
        self._engine.whois_ready.connect(self._on_whois)
        self._engine.error_occurred.connect(self._on_error)
        self._engine.finished.connect(self._on_finished)

    def notify_host(self, host: str):
        self._lookup_combo.lineEdit().setText(host)

    def add_to_history(self, host: str):
        idx = self._lookup_combo.findText(host)
        if idx >= 0:
            self._lookup_combo.removeItem(idx)
        self._lookup_combo.insertItem(0, host)
        self._lookup_combo.setCurrentIndex(0)
        while self._lookup_combo.count() > 15:
            self._lookup_combo.removeItem(self._lookup_combo.count() - 1)

    def get_history(self) -> list:
        return [self._lookup_combo.itemText(i) for i in range(self._lookup_combo.count())]

    def load_history(self, items: list):
        for host in items:
            if self._lookup_combo.findText(host) < 0:
                self._lookup_combo.addItem(host)

    def _lookup(self):
        target = self._lookup_combo.currentText().strip()
        if not target:
            return

        self.add_to_history(target)
        self._target = target
        self._clear_all()
        self._res_grid.set_value("Target", target)
        self._status_lbl.setText(f"Looking up {target}...")
        self._lookup_btn.setEnabled(False)
        self._active_request_id = self._engine.lookup(target)

    def _clear_all(self):
        self._res_grid.clear_values()
        self._geo_grid.clear_values()
        self._whois_grid.clear_values()
        self._dns_table.setRowCount(0)

    def _is_active_request(self, request_id: int, target: str) -> bool:
        return request_id == self._active_request_id and target == self._target

    @Slot(int, str, str)
    def _on_ip_resolved(self, request_id: int, target: str, ip: str):
        if not self._is_active_request(request_id, target):
            return
        self._res_grid.set_value("Resolved IP", ip)

    @Slot(int, str, str)
    def _on_rdns(self, request_id: int, target: str, hostname: str):
        if not self._is_active_request(request_id, target):
            return
        self._res_grid.set_value("Reverse DNS", hostname)

    @Slot(int, str, list)
    def _on_dns(self, request_id: int, target: str, records: list):
        if not self._is_active_request(request_id, target):
            return

        self._dns_table.setRowCount(0)
        order = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]
        sorted_records = sorted(
            records,
            key=lambda record: (order.index(record.rtype) if record.rtype in order else 99, record.value),
        )
        type_colors = {
            "A": C_GREEN,
            "AAAA": C_GREEN,
            "MX": C_BLUE,
            "NS": C_BLUE,
            "TXT": "#e3b341",
            "CNAME": "#d2a8ff",
            "SOA": C_MUTED,
        }

        for record in sorted_records:
            row = self._dns_table.rowCount()
            self._dns_table.insertRow(row)

            type_item = QTableWidgetItem(record.rtype)
            type_item.setForeground(QColor(type_colors.get(record.rtype, C_TEXT)))
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._dns_table.setItem(row, 0, type_item)

            ttl_item = QTableWidgetItem(str(record.ttl))
            ttl_item.setForeground(QColor(C_MUTED))
            ttl_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._dns_table.setItem(row, 1, ttl_item)
            self._dns_table.setItem(row, 2, QTableWidgetItem(record.value))

    @Slot(int, str, object)
    def _on_geo(self, request_id: int, target: str, geo: GeoInfo):
        if not self._is_active_request(request_id, target):
            return
        self._geo_grid.set_value("Country", f"{geo.country} ({geo.country_code})")
        self._geo_grid.set_value("Region", geo.region)
        self._geo_grid.set_value("City", geo.city)
        self._geo_grid.set_value("Timezone", geo.timezone)
        self._geo_grid.set_value("ISP", geo.isp)
        self._geo_grid.set_value("Organisation", geo.org)
        self._geo_grid.set_value("ASN", geo.asn)
        self._geo_grid.set_value("Coordinates", f"{geo.lat:.4f}, {geo.lon:.4f}")

    @Slot(int, str, object)
    def _on_whois(self, request_id: int, target: str, whois_info: WhoisInfo):
        if not self._is_active_request(request_id, target):
            return
        self._whois_grid.set_value("Domain", whois_info.domain)
        self._whois_grid.set_value("Registrar", whois_info.registrar)
        self._whois_grid.set_value("Created", whois_info.creation_date)
        self._whois_grid.set_value("Expires", whois_info.expiration_date)
        self._whois_grid.set_value("Updated", whois_info.updated_date)
        self._whois_grid.set_value("Name Servers", "\n".join(whois_info.name_servers[:6]))
        self._whois_grid.set_value("Status", "\n".join(whois_info.status[:3]))
        self._whois_grid.set_value("Registrant", whois_info.registrant_name)
        self._whois_grid.set_value("Org", whois_info.registrant_org)
        self._whois_grid.set_value("Country", whois_info.registrant_country)
        self._whois_grid.set_value("Emails", ", ".join(whois_info.emails[:3]))

    @Slot(int, str, str)
    def _on_error(self, request_id: int, section: str, message: str):
        if request_id != self._active_request_id:
            return
        self._status_lbl.setText(f"Warning: {section}: {message}")

    @Slot(int, object)
    def _on_finished(self, request_id: int, result):
        if request_id != self._active_request_id or result.target != self._target:
            return
        self._status_lbl.setText(f"Lookup complete for {result.target}")
        self._lookup_btn.setEnabled(True)
