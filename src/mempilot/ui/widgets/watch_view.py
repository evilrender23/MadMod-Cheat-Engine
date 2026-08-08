"""Dense watch-list editor backed exclusively by ``AppController``."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QItemSelection, QSettings, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from mempilot.controller import Actor, AppController
from mempilot.core.data_types import NUMERIC_TYPES, DataType
from mempilot.core.watcher import WatchEntry, WatchSpec
from mempilot.i18n import t
from mempilot.ui.dialogs.pointer_dialog import PointerDialog
from mempilot.ui.models.watch_model import WatchColumn, WatchModel
from mempilot.ui.theme import monospace_font


class _AddressDialog(QDialog):
    """Collect a fixed-width absolute watch without bypassing the facade."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("watch.address_dialog.title"))
        self.setModal(True)

        self.name_edit = QLineEdit(t("watch.address_dialog.default_name"), self)
        self.name_edit.setAccessibleName(t("watch.accessible.address_name"))
        self.address_edit = QLineEdit(self)
        self.address_edit.setFont(monospace_font())
        self.address_edit.setPlaceholderText(t("watch.address_dialog.address_placeholder"))
        self.address_edit.setAccessibleName(t("watch.accessible.absolute_address"))
        self.type_combo = QComboBox(self)
        self.type_combo.setAccessibleName(t("watch.accessible.address_type"))
        for data_type in DataType:
            if data_type in NUMERIC_TYPES:
                self.type_combo.addItem(t(f"watch.type.{data_type.value}"), data_type)
        self.interval_spin = QSpinBox(self)
        self.interval_spin.setRange(50, 5000)
        self.interval_spin.setSingleStep(50)
        self.interval_spin.setValue(100)
        self.interval_spin.setSuffix(t("watch.interval_suffix"))
        self.interval_spin.setAccessibleName(t("watch.accessible.address_interval"))
        self.notes_edit = QLineEdit(self)
        self.notes_edit.setAccessibleName(t("watch.accessible.address_notes"))
        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setAccessibleName(t("watch.accessible.address_error"))

        form = QFormLayout()
        form.addRow(t("watch.label.name"), self.name_edit)
        form.addRow(t("watch.label.address"), self.address_edit)
        form.addRow(t("watch.label.type"), self.type_combo)
        form.addRow(t("watch.label.interval"), self.interval_spin)
        form.addRow(t("watch.label.notes"), self.notes_edit)

        self.add_button = QPushButton(t("watch.action.confirm_add"), self)
        self.add_button.setAccessibleName(t("watch.accessible.confirm_add"))
        self.add_button.clicked.connect(self._validate_and_accept)
        self.cancel_button = QPushButton(t("watch.action.cancel"), self)
        self.cancel_button.setAccessibleName(t("watch.accessible.cancel_add"))
        self.cancel_button.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.add_button)
        actions.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(actions)

        controls = (
            self.name_edit,
            self.address_edit,
            self.type_combo,
            self.interval_spin,
            self.notes_edit,
            self.add_button,
            self.cancel_button,
        )
        for index in range(len(controls) - 1):
            QWidget.setTabOrder(controls[index], controls[index + 1])

    def watch_spec(self) -> WatchSpec:
        """Return the validated absolute watch described by the form."""
        name = self.name_edit.text().strip()
        if not name:
            raise ValueError(t("watch.error.name_required"))
        address = self._parse_address(self.address_edit.text())
        data_type = self.type_combo.currentData()
        if not isinstance(data_type, DataType):
            raise ValueError(t("watch.error.type_required"))
        return WatchSpec(
            label=name,
            data_type=data_type,
            address=address,
            interval_ms=self.interval_spin.value(),
            notes=self.notes_edit.text().strip(),
        )

    @Slot()
    def _validate_and_accept(self) -> None:
        try:
            self.watch_spec()
        except ValueError as exc:
            self.error_label.setText(str(exc))
            return
        self.accept()

    @staticmethod
    def _parse_address(text: str) -> int:
        value = text.strip().lower()
        if value.startswith("0x"):
            value = value[2:]
        elif value.endswith("h"):
            value = value[:-1]
        if not value:
            raise ValueError(t("watch.error.address_required"))
        try:
            address = int(value, 16)
        except ValueError as exc:
            raise ValueError(t("watch.error.invalid_address")) from exc
        if address < 0:
            raise ValueError(t("watch.error.invalid_address"))
        return address


class WatchView(QWidget):
    """Watch table with editing, freezing and workspace actions."""

    workspace_saved = Signal(object)
    workspace_loaded = Signal(object)

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._settings = QSettings("MemPilot", "MemPilot")
        self.model = WatchModel(controller, self)
        self.model.operation_failed.connect(self._show_error)

        self.table = QTableView(self)
        self.table.setModel(self.model)
        self.table.setAccessibleName(t("watch.accessible.table"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(WatchColumn.NAME, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(WatchColumn.ADDRESS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WatchColumn.DATA_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WatchColumn.VALUE, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(WatchColumn.DESIRED, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(WatchColumn.FROZEN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WatchColumn.INTERVAL, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(WatchColumn.NOTES, QHeaderView.ResizeMode.Stretch)

        self.add_address_button = QPushButton(t("watch.action.add_address"), self)
        self.add_address_button.setAccessibleName(t("watch.accessible.add_address"))
        self.add_address_button.clicked.connect(self._add_address)
        self.add_pointer_button = QPushButton(t("watch.action.add_pointer"), self)
        self.add_pointer_button.setAccessibleName(t("watch.accessible.add_pointer"))
        self.add_pointer_button.clicked.connect(self._add_pointer)
        self.remove_button = QPushButton(t("watch.action.remove"), self)
        self.remove_button.setAccessibleName(t("watch.accessible.remove"))
        self.remove_button.clicked.connect(self._remove_selected)
        self.freeze_all_button = QPushButton(t("watch.action.freeze_all"), self)
        self.freeze_all_button.setAccessibleName(t("watch.accessible.freeze_all"))
        self.freeze_all_button.clicked.connect(self._freeze_all)
        self.unfreeze_all_button = QPushButton(t("watch.action.unfreeze_all"), self)
        self.unfreeze_all_button.setAccessibleName(t("watch.accessible.unfreeze_all"))
        self.unfreeze_all_button.clicked.connect(self._unfreeze_all)
        self.save_workspace_button = QPushButton(t("watch.action.save_workspace"), self)
        self.save_workspace_button.setAccessibleName(t("watch.accessible.save_workspace"))
        self.save_workspace_button.clicked.connect(self._save_workspace)
        self.load_workspace_button = QPushButton(t("watch.action.load_workspace"), self)
        self.load_workspace_button.setAccessibleName(t("watch.accessible.load_workspace"))
        self.load_workspace_button.clicked.connect(self._load_workspace)

        actions = QHBoxLayout()
        actions.addWidget(self.add_address_button)
        actions.addWidget(self.add_pointer_button)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.freeze_all_button)
        actions.addWidget(self.unfreeze_all_button)
        actions.addStretch(1)
        actions.addWidget(self.save_workspace_button)
        actions.addWidget(self.load_workspace_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)

        selection_model = self.table.selectionModel()
        selection_model.selectionChanged.connect(self._selection_changed)
        self._selection_changed(QItemSelection(), QItemSelection())
        self._set_tab_order()

    @Slot()
    def _add_address(self) -> None:
        dialog = _AddressDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._controller.add_watch(dialog.watch_spec(), Actor.USER)
        except Exception as exc:
            self._show_error(str(exc))

    @Slot()
    def _add_pointer(self) -> None:
        PointerDialog(self._controller, self).exec()

    @Slot()
    def _remove_selected(self) -> None:
        entries = self._selected_entries()
        for entry in entries:
            try:
                self._controller.remove_watch(entry.id, Actor.USER)
            except Exception as exc:
                self._show_error(str(exc))
                return

    @Slot()
    def _freeze_all(self) -> None:
        missing = 0
        for entry in self._controller.list_watches():
            if entry.frozen:
                continue
            desired = entry.desired_value or entry.current_value
            if not desired:
                missing += 1
                continue
            try:
                self._controller.set_freeze(entry.id, True, desired, entry.interval_ms, Actor.USER)
            except Exception as exc:
                self._show_error(str(exc))
                return
        if missing:
            self._show_message(
                QMessageBox.Icon.Warning,
                t("watch.warning.title"),
                t("watch.warning.freeze_missing", count=missing),
            )

    @Slot()
    def _unfreeze_all(self) -> None:
        for entry in self._controller.list_watches():
            if not entry.frozen:
                continue
            try:
                self._controller.set_freeze(
                    entry.id,
                    False,
                    entry.desired_value,
                    entry.interval_ms,
                    Actor.USER,
                )
            except Exception as exc:
                self._show_error(str(exc))
                return

    @Slot()
    def _save_workspace(self) -> None:
        directory = self._workspace_directory()
        path_text, _selected_filter = QFileDialog.getSaveFileName(
            self,
            t("watch.workspace.save_title"),
            directory,
            t("watch.workspace.filter"),
        )
        if not path_text:
            return
        path = Path(path_text)
        if path.suffix.casefold() != ".json":
            path = path.with_suffix(".json")
        try:
            self._controller.save_workspace(path, Actor.USER)
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._remember_workspace_directory(path)
        self.workspace_saved.emit(path)

    @Slot()
    def _load_workspace(self) -> None:
        path_text, _selected_filter = QFileDialog.getOpenFileName(
            self,
            t("watch.workspace.load_title"),
            self._workspace_directory(),
            t("watch.workspace.filter"),
        )
        if not path_text:
            return
        path = Path(path_text)
        try:
            self._controller.load_workspace(path, Actor.USER)
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._remember_workspace_directory(path)
        self.workspace_loaded.emit(path)

    @Slot(QItemSelection, QItemSelection)
    def _selection_changed(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        del selected, deselected
        self.remove_button.setEnabled(bool(self._selected_entries()))

    @Slot(str)
    def _show_error(self, message: str) -> None:
        self._show_message(QMessageBox.Icon.Critical, t("watch.error.title"), message)

    def _show_message(self, icon: QMessageBox.Icon, title: str, text: str) -> None:
        box = QMessageBox(icon, title, text, QMessageBox.StandardButton.Ok, self)
        ok_button = box.button(QMessageBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText(t("watch.action.close"))
        box.exec()

    def _selected_entries(self) -> list[WatchEntry]:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        return [entry for row in rows if (entry := self.model.entry_at(row)) is not None]

    def _workspace_directory(self) -> str:
        value = self._settings.value("watch/workspace_dir", "")
        return value if isinstance(value, str) else ""

    def _remember_workspace_directory(self, path: Path) -> None:
        self._settings.setValue("watch/workspace_dir", str(path.parent))

    def _set_tab_order(self) -> None:
        controls = (
            self.table,
            self.add_address_button,
            self.add_pointer_button,
            self.remove_button,
            self.freeze_all_button,
            self.unfreeze_all_button,
            self.save_workspace_button,
            self.load_workspace_button,
        )
        for index in range(len(controls) - 1):
            QWidget.setTabOrder(controls[index], controls[index + 1])
