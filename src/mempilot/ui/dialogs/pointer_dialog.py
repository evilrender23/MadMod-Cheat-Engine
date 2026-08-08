"""Pointer-chain editor and resolver using only the public controller facade."""

from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mempilot.controller import Actor, AppController
from mempilot.core.data_types import NUMERIC_TYPES, DataType, format_hex
from mempilot.core.pointer_chain import ChainResolution, PointerChain
from mempilot.core.watcher import WatchEntry, WatchSpec
from mempilot.i18n import t
from mempilot.ui.theme import monospace_font


class PointerDialog(QDialog):
    """Edit, resolve and register one module-relative pointer chain."""

    watch_saved = Signal(object)

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._chain_id = uuid4().hex[:12]
        self._last_chain: PointerChain | None = None
        self._last_resolution: ChainResolution | None = None
        self.saved_watch: WatchEntry | None = None
        self._fixed_font = monospace_font()

        self.setWindowTitle(t("pointer.title"))
        self.setModal(True)

        self.name_edit = QLineEdit(t("pointer.default_name"), self)
        self.name_edit.setAccessibleName(t("pointer.accessible.name"))
        self.module_combo = QComboBox(self)
        self.module_combo.setAccessibleName(t("pointer.accessible.module"))
        self.base_offset_edit = QLineEdit("0x0", self)
        self.base_offset_edit.setFont(self._fixed_font)
        self.base_offset_edit.setAccessibleName(t("pointer.accessible.base_offset"))
        self.type_combo = QComboBox(self)
        self.type_combo.setAccessibleName(t("pointer.accessible.type"))
        for data_type in DataType:
            if data_type in NUMERIC_TYPES:
                self.type_combo.addItem(t(f"watch.type.{data_type.value}"), data_type)

        form = QFormLayout()
        form.addRow(t("pointer.label.name"), self.name_edit)
        form.addRow(t("pointer.label.module"), self.module_combo)
        form.addRow(t("pointer.label.base_offset"), self.base_offset_edit)
        form.addRow(t("pointer.label.type"), self.type_combo)

        self.offsets_list = QListWidget(self)
        self.offsets_list.setAccessibleName(t("pointer.accessible.offsets"))
        self.offsets_list.itemChanged.connect(self._normalize_edited_offset)
        self.offset_edit = QLineEdit(self)
        self.offset_edit.setFont(self._fixed_font)
        self.offset_edit.setPlaceholderText(t("pointer.offset.placeholder"))
        self.offset_edit.setAccessibleName(t("pointer.accessible.new_offset"))
        self.offset_edit.returnPressed.connect(self._add_offset)
        self.add_offset_button = QPushButton(t("pointer.action.add_offset"), self)
        self.add_offset_button.setAccessibleName(t("pointer.accessible.add_offset"))
        self.add_offset_button.clicked.connect(self._add_offset)
        self.remove_offset_button = QPushButton(t("pointer.action.remove_offset"), self)
        self.remove_offset_button.setAccessibleName(t("pointer.accessible.remove_offset"))
        self.remove_offset_button.clicked.connect(self._remove_selected_offsets)

        offset_actions = QHBoxLayout()
        offset_actions.addWidget(self.offset_edit, 1)
        offset_actions.addWidget(self.add_offset_button)
        offset_actions.addWidget(self.remove_offset_button)
        offsets_layout = QVBoxLayout()
        offsets_layout.addWidget(self.offsets_list)
        offsets_layout.addLayout(offset_actions)
        offsets_group = QGroupBox(t("pointer.group.offsets"), self)
        offsets_group.setLayout(offsets_layout)

        self.steps_table = QTableWidget(0, 4, self)
        self.steps_table.setHorizontalHeaderLabels(
            [
                t("pointer.column.index"),
                t("pointer.column.address"),
                t("pointer.column.value"),
                t("pointer.column.ok"),
            ]
        )
        self.steps_table.setAccessibleName(t("pointer.accessible.steps"))
        self.steps_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.steps_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.steps_table.verticalHeader().setVisible(False)
        header = self.steps_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self.final_address_label = QLabel(t("pointer.final.pending"), self)
        self.final_address_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.final_address_label.setAccessibleName(t("pointer.accessible.final_address"))
        self.final_value_label = QLabel(t("pointer.final_value.pending"), self)
        self.final_value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.final_value_label.setAccessibleName(t("pointer.accessible.final_value"))
        self.status_label = QLabel(t("pointer.status.ready"), self)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName(t("pointer.accessible.status"))

        resolution_layout = QVBoxLayout()
        resolution_layout.addWidget(self.steps_table)
        resolution_layout.addWidget(self.final_address_label)
        resolution_layout.addWidget(self.final_value_label)
        resolution_layout.addWidget(self.status_label)
        resolution_group = QGroupBox(t("pointer.group.resolution"), self)
        resolution_group.setLayout(resolution_layout)

        self.resolve_button = QPushButton(t("pointer.action.resolve"), self)
        self.resolve_button.setAccessibleName(t("pointer.accessible.resolve"))
        self.resolve_button.clicked.connect(self.resolve)
        self.save_button = QPushButton(t("pointer.action.save"), self)
        self.save_button.setAccessibleName(t("pointer.accessible.save"))
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_to_workspace)
        self.cancel_button = QPushButton(t("pointer.action.cancel"), self)
        self.cancel_button.setAccessibleName(t("pointer.accessible.cancel"))
        self.cancel_button.clicked.connect(self.reject)

        actions = QHBoxLayout()
        actions.addWidget(self.resolve_button)
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        actions.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(offsets_group)
        layout.addWidget(resolution_group, 1)
        layout.addLayout(actions)
        self.name_edit.textEdited.connect(lambda _text: self._invalidate_resolution())
        self.base_offset_edit.textEdited.connect(lambda _text: self._invalidate_resolution())
        self.module_combo.currentIndexChanged.connect(lambda _index: self._invalidate_resolution())
        self.type_combo.currentIndexChanged.connect(lambda _index: self._invalidate_resolution())

        self._load_modules()
        self._set_tab_order()

    @Slot()
    def resolve(self) -> None:
        """Resolve the edited chain and display every diagnostic step."""
        try:
            chain = self._build_chain()
            resolution = self._controller.resolve_chain(chain)
        except Exception as exc:
            self._set_failure(str(exc))
            return

        self._last_chain = chain
        self._last_resolution = resolution
        self._populate_steps(resolution)
        if resolution.final_address is None:
            self.final_address_label.setText(t("pointer.final.unresolved"))
            self.final_value_label.setText(t("pointer.final_value.unavailable"))
            self.status_label.setText(resolution.error or t("pointer.status.resolve_failed"))
            self.save_button.setEnabled(False)
            return

        self.final_address_label.setText(
            t("pointer.final.address", address=format_hex(resolution.final_address))
        )
        try:
            value = self._controller.read_address(resolution.final_address, chain.data_type)
        except Exception as exc:
            self.final_value_label.setText(t("pointer.final_value.unavailable"))
            self.status_label.setText(t("pointer.status.value_failed", error=str(exc)))
            self.save_button.setEnabled(False)
            return
        self.final_value_label.setText(t("pointer.final.value", value=value))
        self.status_label.setText(t("pointer.status.resolved"))
        self.save_button.setEnabled(True)

    @Slot()
    def save_to_workspace(self) -> None:
        """Register the resolved chain as a watch in controller workspace state."""
        try:
            chain = self._build_chain()
            if (
                self._last_chain != chain
                or self._last_resolution is None
                or self._last_resolution.final_address is None
            ):
                raise ValueError(t("pointer.error.resolve_before_save"))
            entry = self._controller.add_watch(
                WatchSpec(
                    label=chain.label,
                    data_type=chain.data_type,
                    chain=chain,
                ),
                Actor.USER,
            )
        except Exception as exc:
            self._set_failure(str(exc))
            return
        self.saved_watch = entry
        self.watch_saved.emit(entry)
        self.accept()

    @Slot()
    def _add_offset(self) -> None:
        text = self.offset_edit.text().strip()
        try:
            value = self._parse_offset(text)
        except ValueError:
            self.status_label.setText(t("pointer.error.invalid_offset", value=text))
            self.offset_edit.selectAll()
            self.offset_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        item = QListWidgetItem(self._format_offset(value))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setFont(self._fixed_font)
        self.offsets_list.addItem(item)
        self.offsets_list.setCurrentItem(item)
        self.offset_edit.clear()
        self._invalidate_resolution()

    @Slot()
    def _remove_selected_offsets(self) -> None:
        for item in self.offsets_list.selectedItems():
            self.offsets_list.takeItem(self.offsets_list.row(item))
        self._invalidate_resolution()

    @Slot(QListWidgetItem)
    def _normalize_edited_offset(self, item: QListWidgetItem) -> None:
        try:
            value = self._parse_offset(item.text())
        except ValueError:
            self.status_label.setText(t("pointer.error.invalid_offset", value=item.text()))
            self.save_button.setEnabled(False)
            return
        normalized = self._format_offset(value)
        if item.text() != normalized:
            item.setText(normalized)
        self._invalidate_resolution()

    def _load_modules(self) -> None:
        try:
            modules = self._controller.list_modules(Actor.USER)
        except Exception as exc:
            self.module_combo.setEnabled(False)
            self.resolve_button.setEnabled(False)
            self.status_label.setText(t("pointer.error.modules", error=str(exc)))
            return
        for module in sorted(modules, key=lambda item: item.name.casefold()):
            self.module_combo.addItem(
                t(
                    "pointer.module.item",
                    name=module.name,
                    base=format_hex(module.base),
                ),
                module.name,
            )
        if self.module_combo.count() == 0:
            self.module_combo.setEnabled(False)
            self.resolve_button.setEnabled(False)
            self.status_label.setText(t("pointer.error.no_modules"))

    def _build_chain(self) -> PointerChain:
        label = self.name_edit.text().strip()
        if not label:
            raise ValueError(t("pointer.error.name_required"))
        module = self.module_combo.currentData()
        if not isinstance(module, str) or not module:
            raise ValueError(t("pointer.error.module_required"))
        try:
            base_offset = self._parse_hex_address(self.base_offset_edit.text())
        except ValueError as exc:
            raise ValueError(t("pointer.error.invalid_base_offset")) from exc
        offsets = [
            self._parse_offset(self.offsets_list.item(row).text())
            for row in range(self.offsets_list.count())
        ]
        if not offsets:
            raise ValueError(t("pointer.error.offset_required"))
        raw_data_type = self.type_combo.currentData()
        try:
            data_type = (
                raw_data_type
                if isinstance(raw_data_type, DataType)
                else DataType(str(raw_data_type))
            )
        except ValueError as exc:
            raise ValueError(t("pointer.error.type_required")) from exc
        return PointerChain(
            id=self._chain_id,
            label=label,
            module=module,
            base_offset=base_offset,
            offsets=offsets,
            data_type=data_type,
        )

    def _populate_steps(self, resolution: ChainResolution) -> None:
        self.steps_table.setRowCount(len(resolution.steps))
        for row, step in enumerate(resolution.steps):
            address_item = QTableWidgetItem(format_hex(step.address))
            address_item.setFont(self._fixed_font)
            pointer_text = (
                format_hex(step.pointer_value)
                if step.pointer_value is not None
                else t("pointer.value.unavailable")
            )
            pointer_item = QTableWidgetItem(pointer_text)
            pointer_item.setFont(self._fixed_font)
            ok_item = QTableWidgetItem(t("pointer.value.yes") if step.ok else t("pointer.value.no"))
            ok_item.setToolTip(step.note)
            self.steps_table.setItem(row, 0, QTableWidgetItem(str(step.index)))
            self.steps_table.setItem(row, 1, address_item)
            self.steps_table.setItem(row, 2, pointer_item)
            self.steps_table.setItem(row, 3, ok_item)

    def _invalidate_resolution(self) -> None:
        self._last_chain = None
        self._last_resolution = None
        self.save_button.setEnabled(False)
        self.final_address_label.setText(t("pointer.final.pending"))
        self.final_value_label.setText(t("pointer.final_value.pending"))
        self.status_label.setText(t("pointer.status.ready"))

    def _set_failure(self, message: str) -> None:
        self._last_chain = None
        self._last_resolution = None
        self.save_button.setEnabled(False)
        self.status_label.setText(message)

    def _set_tab_order(self) -> None:
        controls = (
            self.name_edit,
            self.module_combo,
            self.base_offset_edit,
            self.type_combo,
            self.offsets_list,
            self.offset_edit,
            self.add_offset_button,
            self.remove_offset_button,
            self.resolve_button,
            self.save_button,
            self.cancel_button,
        )
        for index in range(len(controls) - 1):
            QWidget.setTabOrder(controls[index], controls[index + 1])

    @staticmethod
    def _parse_hex_address(text: str) -> int:
        value = text.strip().lower()
        if value.startswith("0x"):
            value = value[2:]
        elif value.endswith("h"):
            value = value[:-1]
        if not value:
            raise ValueError
        parsed = int(value, 16)
        if parsed < 0:
            raise ValueError
        return parsed

    @staticmethod
    def _parse_offset(text: str) -> int:
        value = text.strip().lower()
        if not value:
            raise ValueError
        sign = -1 if value.startswith("-") else 1
        if value[0] in "+-":
            value = value[1:]
        if value.startswith("0x"):
            value = value[2:]
        elif value.endswith("h"):
            value = value[:-1]
        if not value:
            raise ValueError
        return sign * int(value, 16)

    @staticmethod
    def _format_offset(value: int) -> str:
        sign = "-" if value < 0 else ""
        return f"{sign}0x{abs(value):X}"
