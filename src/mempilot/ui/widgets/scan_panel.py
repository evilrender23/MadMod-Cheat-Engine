"""Scan request editor with live, type-aware validation."""

from __future__ import annotations

from itertools import pairwise
from typing import cast

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QDoubleValidator, QKeySequence, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mempilot.config.settings import Settings
from mempilot.controller import ScanStatus
from mempilot.core.data_types import FLOAT_TYPES, NUMERIC_TYPES, DataType
from mempilot.core.scan_session import SessionState
from mempilot.core.scanner import ScanMode, ScanOptions, ScanRequest
from mempilot.i18n import t
from mempilot.ui.theme import SPACE_1, SPACE_2, SPACE_3, monospace_font

_VALUELESS_MODES = {
    ScanMode.UNKNOWN_INITIAL,
    ScanMode.CHANGED,
    ScanMode.UNCHANGED,
    ScanMode.INCREASED,
    ScanMode.DECREASED,
}
_MODE_KEYS = {mode: f"scan.mode.{mode.value}" for mode in ScanMode}


class ScanPanel(QWidget):
    """Build valid scan requests and communicate mutually exclusive actions."""

    first_scan_requested = Signal(object)
    next_scan_requested = Signal(object)
    reset_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, settings: Settings | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("scanPanel")
        self.setMinimumWidth(300)
        self._settings = settings or Settings()
        self._state = SessionState.NEW
        self._attached = False
        self._build_ui()
        self._populate_data_types()
        self._on_data_type_changed()
        self._validate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.data_type_combo = QComboBox(self)
        self.data_type_combo.setAccessibleName(t("scan.data_type"))
        self.data_type_combo.currentIndexChanged.connect(self._on_data_type_changed)
        form.addRow(t("scan.data_type"), self.data_type_combo)

        self.mode_combo = QComboBox(self)
        self.mode_combo.setAccessibleName(t("scan.condition"))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow(t("scan.condition"), self.mode_combo)

        self.value_edit = QLineEdit(self)
        self.value_edit.setAccessibleName(t("scan.value"))
        self.value_edit.setFont(monospace_font())
        self.value_edit.textChanged.connect(self._validate)
        form.addRow(t("scan.value"), self.value_edit)

        self.value2_label = QLabel(t("scan.value2"), self)
        self.value2_edit = QLineEdit(self)
        self.value2_edit.setAccessibleName(t("scan.value2"))
        self.value2_edit.setFont(monospace_font())
        self.value2_edit.textChanged.connect(self._validate)
        form.addRow(self.value2_label, self.value2_edit)

        self.validation_label = QLabel("", self)
        self.validation_label.setObjectName("scanValidation")
        self.validation_label.setProperty("tone", "error")
        self.validation_label.setWordWrap(True)
        layout.addLayout(form)
        layout.addWidget(self.validation_label)

        self.tolerance_row = QWidget(self)
        tolerance_layout = QHBoxLayout(self.tolerance_row)
        tolerance_layout.setContentsMargins(0, 0, 0, 0)
        tolerance_layout.setSpacing(SPACE_2)
        self.tolerance_check = QCheckBox(t("scan.use_tolerance"), self.tolerance_row)
        self.tolerance_check.setAccessibleName(t("scan.use_tolerance"))
        self.tolerance_check.setChecked(self._settings.scan.use_tolerance)
        self.tolerance_check.toggled.connect(self._validate)
        self.tolerance_edit = QLineEdit(
            str(self._settings.scan.float_tolerance), self.tolerance_row
        )
        self.tolerance_edit.setAccessibleName(t("scan.tolerance"))
        self.tolerance_edit.setValidator(QDoubleValidator(0.0, 1.0e100, 12, self))
        self.tolerance_edit.textChanged.connect(self._validate)
        tolerance_layout.addWidget(self.tolerance_check)
        tolerance_layout.addWidget(QLabel(t("scan.tolerance"), self.tolerance_row))
        tolerance_layout.addWidget(self.tolerance_edit, 1)
        layout.addWidget(self.tolerance_row)

        self.case_check = QCheckBox(t("scan.case_sensitive"), self)
        self.case_check.setAccessibleName(t("scan.case_sensitive"))
        self.case_check.setChecked(self._settings.scan.case_sensitive)
        self.case_check.toggled.connect(self._validate)
        layout.addWidget(self.case_check)

        self.regions_toggle = QToolButton(self)
        self.regions_toggle.setText(t("scan.regions"))
        self.regions_toggle.setAccessibleName(t("scan.regions"))
        self.regions_toggle.setCheckable(True)
        self.regions_toggle.setChecked(False)
        self.regions_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.regions_toggle.toggled.connect(self._toggle_regions)
        layout.addWidget(self.regions_toggle)

        self.regions_widget = QFrame(self)
        regions = QGridLayout(self.regions_widget)
        regions.setContentsMargins(SPACE_2, SPACE_1, SPACE_2, SPACE_2)
        regions.setSpacing(SPACE_2)
        self.writable_check = QCheckBox(t("scan.writable_only"), self.regions_widget)
        self.writable_check.setAccessibleName(t("scan.writable_only"))
        self.writable_check.setChecked(self._settings.scan.writable_only)
        self.image_check = QCheckBox(t("scan.include_image"), self.regions_widget)
        self.image_check.setAccessibleName(t("scan.include_image"))
        self.image_check.setChecked(self._settings.scan.include_image)
        self.mapped_check = QCheckBox(t("scan.include_mapped"), self.regions_widget)
        self.mapped_check.setAccessibleName(t("scan.include_mapped"))
        self.mapped_check.setChecked(self._settings.scan.include_mapped)
        regions.addWidget(self.writable_check, 0, 0, 1, 2)
        regions.addWidget(self.image_check, 1, 0)
        regions.addWidget(self.mapped_check, 1, 1)

        self.alignment_combo = QComboBox(self.regions_widget)
        self.alignment_combo.setAccessibleName(t("scan.alignment"))
        self.alignment_combo.addItem(t("scan.alignment.auto"), 0)
        self.alignment_combo.addItem(t("scan.alignment.byte"), 1)
        if self._settings.scan.alignment == 1:
            self.alignment_combo.setCurrentIndex(1)
        regions.addWidget(QLabel(t("scan.alignment"), self.regions_widget), 2, 0)
        regions.addWidget(self.alignment_combo, 2, 1)

        self.address_min_edit = QLineEdit(
            f"0x{self._settings.scan.address_min:X}", self.regions_widget
        )
        self.address_min_edit.setAccessibleName(t("scan.address_min"))
        self.address_min_edit.setFont(monospace_font())
        self.address_min_edit.textChanged.connect(self._validate)
        self.address_max_edit = QLineEdit(
            f"0x{self._settings.scan.address_max:X}", self.regions_widget
        )
        self.address_max_edit.setAccessibleName(t("scan.address_max"))
        self.address_max_edit.setFont(monospace_font())
        self.address_max_edit.textChanged.connect(self._validate)
        regions.addWidget(QLabel(t("scan.address_min"), self.regions_widget), 3, 0)
        regions.addWidget(self.address_min_edit, 3, 1)
        regions.addWidget(QLabel(t("scan.address_max"), self.regions_widget), 4, 0)
        regions.addWidget(self.address_max_edit, 4, 1)
        self.regions_widget.setVisible(False)
        layout.addWidget(self.regions_widget)

        buttons = QHBoxLayout()
        buttons.setSpacing(SPACE_1)
        self.first_button = QPushButton(t("action.first_scan"), self)
        self.first_button.setAccessibleName(t("action.first_scan"))
        self.first_button.setShortcut(QKeySequence("F5"))
        self.first_button.setProperty("primary", True)
        self.first_button.clicked.connect(self._emit_first)
        self.next_button = QPushButton(t("action.next_scan"), self)
        self.next_button.setAccessibleName(t("action.next_scan"))
        self.next_button.setShortcut(QKeySequence("F6"))
        self.next_button.clicked.connect(self._emit_next)
        buttons.addWidget(self.first_button)
        buttons.addWidget(self.next_button)
        layout.addLayout(buttons)

        secondary = QHBoxLayout()
        secondary.setSpacing(SPACE_1)
        self.reset_button = QPushButton(t("action.reset"), self)
        self.reset_button.setAccessibleName(t("action.reset"))
        self.reset_button.setShortcut(QKeySequence("Ctrl+R"))
        self.reset_button.clicked.connect(self.reset_requested)
        self.cancel_button = QPushButton(t("action.cancel"), self)
        self.cancel_button.setAccessibleName(t("action.cancel"))
        self.cancel_button.setShortcut(QKeySequence("Esc"))
        self.cancel_button.clicked.connect(self.cancel_requested)
        secondary.addWidget(self.reset_button)
        secondary.addWidget(self.cancel_button)
        layout.addLayout(secondary)

        stats = QGroupBox(t("scan.statistics"), self)
        stats_layout = QFormLayout(stats)
        self.stats: dict[str, QLabel] = {}
        for key in ("candidates", "regions", "bytes", "duration", "refinements", "last"):
            label = QLabel("—", stats)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            stats_layout.addRow(t(f"scan.stat.{key}"), label)
            self.stats[key] = label
        layout.addWidget(stats)
        layout.addStretch(1)

        tab_order = [
            self.data_type_combo,
            self.mode_combo,
            self.value_edit,
            self.value2_edit,
            self.tolerance_check,
            self.tolerance_edit,
            self.case_check,
            self.regions_toggle,
            self.first_button,
            self.next_button,
            self.reset_button,
            self.cancel_button,
        ]
        for before, after in pairwise(tab_order):
            QWidget.setTabOrder(before, after)

    def _populate_data_types(self) -> None:
        for data_type in DataType:
            self.data_type_combo.addItem(t(f"data_type.{data_type.value}"), data_type)
            if data_type is DataType.BYTES:
                model = cast(QStandardItemModel, self.data_type_combo.model())
                item = model.item(self.data_type_combo.count() - 1)
                if item is not None:
                    item.setEnabled(False)
        index = self.data_type_combo.findData(DataType.INT32)
        self.data_type_combo.setCurrentIndex(max(0, index))

    def current_request(self) -> ScanRequest:
        """Build and validate the complete immutable request from controls."""
        data_type = self.current_data_type()
        mode = self.current_mode()
        value = None if mode in _VALUELESS_MODES else self.value_edit.text().strip() or None
        value2 = self.value2_edit.text().strip() or None if mode is ScanMode.BETWEEN else None
        tolerance_text = self.tolerance_edit.text().strip().replace(",", ".")
        options = ScanOptions(
            alignment=int(self.alignment_combo.currentData()),
            writable_only=self.writable_check.isChecked(),
            include_image=self.image_check.isChecked(),
            include_mapped=self.mapped_check.isChecked(),
            use_tolerance=self.tolerance_check.isChecked(),
            float_tolerance=float(tolerance_text),
            case_sensitive=self.case_check.isChecked(),
            chunk_size=self._settings.scan.chunk_size,
            max_candidates=self._settings.scan.max_candidates,
            unknown_budget_mb=self._settings.scan.unknown_budget_mb,
            address_min=self._parse_address(self.address_min_edit.text()),
            address_max=self._parse_address(self.address_max_edit.text()),
        )
        request = ScanRequest(data_type, mode, value, value2, options)
        request.validate()
        return request

    def current_data_type(self) -> DataType:
        value = self.data_type_combo.currentData()
        return value if isinstance(value, DataType) else DataType.INT32

    def current_mode(self) -> ScanMode:
        value = self.mode_combo.currentData()
        return value if isinstance(value, ScanMode) else ScanMode.EXACT

    @Slot()
    def _on_data_type_changed(self) -> None:
        data_type = self.current_data_type()
        prior = self.current_mode()
        self.mode_combo.blockSignals(True)
        self.mode_combo.clear()
        for mode in self._available_modes(data_type):
            self.mode_combo.addItem(t(_MODE_KEYS[mode]), mode)
        index = self.mode_combo.findData(prior)
        self.mode_combo.setCurrentIndex(index if index >= 0 else 0)
        self.mode_combo.blockSignals(False)
        self._on_mode_changed()

    @Slot()
    def _on_mode_changed(self) -> None:
        mode = self.current_mode()
        data_type = self.current_data_type()
        needs_value = mode not in _VALUELESS_MODES
        self.value_edit.setVisible(needs_value)
        label = self.sender()
        del label
        self.value2_label.setVisible(mode is ScanMode.BETWEEN)
        self.value2_edit.setVisible(mode is ScanMode.BETWEEN)
        is_float = data_type in FLOAT_TYPES
        self.tolerance_row.setVisible(is_float)
        is_text = data_type in {DataType.STRING_UTF8, DataType.STRING_UTF16}
        self.case_check.setVisible(is_text)
        self._validate()

    @Slot(bool)
    def _toggle_regions(self, expanded: bool) -> None:
        self.regions_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.regions_widget.setVisible(expanded)

    @Slot()
    def _validate(self) -> bool:
        message = ""
        try:
            self.current_request()
        except Exception as exc:
            message = str(exc)
        self.validation_label.setText(message)
        self.validation_label.setVisible(bool(message))
        self.value_edit.setProperty(
            "validationError", bool(message) and self.value_edit.isVisible()
        )
        self.value2_edit.setProperty(
            "validationError", bool(message) and self.value2_edit.isVisible()
        )
        for widget in (self.value_edit, self.value2_edit):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        valid = not message
        self._update_buttons(valid)
        return valid

    def set_session_state(self, state: SessionState, attached: bool) -> None:
        """Apply the mutually exclusive session action matrix."""
        self._state = state
        self._attached = attached
        self._update_buttons(self._validate())

    def update_stats(self, status: ScanStatus) -> None:
        """Render all session statistics without relying on color."""
        progress = status.progress
        self.stats["candidates"].setText(f"{status.candidates:,}".replace(",", "."))
        self.stats["regions"].setText(str(progress.regions_done) if progress is not None else "—")
        self.stats["bytes"].setText(
            f"{progress.bytes_done / (1 << 20):.1f} MB" if progress is not None else "—"
        )
        self.stats["duration"].setText(
            f"{progress.elapsed_s:.1f} s" if progress is not None else "—"
        )
        self.stats["refinements"].setText(str(status.refinements))
        mode = status.last_mode
        self.stats["last"].setText(t(_MODE_KEYS[mode]) if mode is not None else "—")

    def reset_form_state(self) -> None:
        """Return UI session controls to first-scan mode for the same process."""
        self._state = SessionState.NEW
        for label in self.stats.values():
            label.setText("—")
        self._update_buttons(self._validate())

    @Slot()
    def _emit_first(self) -> None:
        if self._validate():
            self.first_scan_requested.emit(self.current_request())

    @Slot()
    def _emit_next(self) -> None:
        if self._validate():
            self.next_scan_requested.emit(self.current_request())

    def _update_buttons(self, valid: bool) -> None:
        scanning = self._state is SessionState.SCANNING
        ready = self._state is SessionState.READY
        self.first_button.setEnabled(self._attached and not scanning and not ready and valid)
        self.next_button.setEnabled(self._attached and ready and valid)
        self.reset_button.setEnabled(self._attached and ready)
        self.cancel_button.setEnabled(scanning)

    @staticmethod
    def _available_modes(data_type: DataType) -> list[ScanMode]:
        if data_type is DataType.AOB:
            return [ScanMode.AOB]
        if data_type in {DataType.STRING_UTF8, DataType.STRING_UTF16}:
            return [ScanMode.TEXT]
        if data_type not in NUMERIC_TYPES:
            return []
        return [
            ScanMode.EXACT,
            ScanMode.UNKNOWN_INITIAL,
            ScanMode.CHANGED,
            ScanMode.UNCHANGED,
            ScanMode.INCREASED,
            ScanMode.DECREASED,
            ScanMode.INCREASED_BY,
            ScanMode.DECREASED_BY,
            ScanMode.BETWEEN,
            ScanMode.GREATER_THAN,
            ScanMode.LESS_THAN,
        ]

    @staticmethod
    def _parse_address(text: str) -> int:
        normalized = text.strip()
        if not normalized:
            raise ValueError(t("scan.validation.address"))
        try:
            return int(normalized, 16)
        except ValueError:
            raise ValueError(t("scan.validation.address")) from None
