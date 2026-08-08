"""Asynchronous, safe process selection dialog."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from mempilot.controller import Actor, AppController
from mempilot.core.backend import ProcessIdentity
from mempilot.core.process_service import ProcessEntry
from mempilot.i18n import t
from mempilot.ui.dialogs.error_dialog import ErrorDialog
from mempilot.ui.models.process_model import ProcessFilterModel, ProcessModel
from mempilot.ui.theme import SPACE_2, SPACE_3


class AttachDialog(QDialog):
    """List processes off the GUI thread and attach with an explicit access level."""

    def __init__(
        self,
        controller: AppController,
        show_system: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self.identity: ProcessIdentity | None = None
        self.write_access = False
        self.setWindowTitle(t("process.title"))
        self.setModal(True)
        self.resize(980, 620)
        self.setMinimumSize(720, 480)
        self._build_ui(show_system)
        controller.processes_listed.connect(self._on_processes)
        controller.process_list_failed.connect(self._on_failure)
        self.refresh()

    def _build_ui(self, show_system: bool) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)
        query_row = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText(t("process.search"))
        self.search_edit.setAccessibleName(t("process.search"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._filter)
        query_row.addWidget(self.search_edit, 1)
        self.system_check = QCheckBox(t("process.show_system"), self)
        self.system_check.setAccessibleName(t("process.show_system"))
        self.system_check.setChecked(show_system)
        self.system_check.toggled.connect(self.refresh)
        query_row.addWidget(self.system_check)
        self.refresh_button = QPushButton(t("process.refresh"), self)
        self.refresh_button.setAccessibleName(t("process.refresh"))
        self.refresh_button.clicked.connect(self.refresh)
        query_row.addWidget(self.refresh_button)
        layout.addLayout(query_row)

        self.source_model = ProcessModel(self)
        self.proxy_model = ProcessFilterModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        self.table = QTableView(self)
        self.table.setAccessibleName(t("process.table_accessible"))
        self.table.setModel(self.proxy_model)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().setVisible(False)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.table.doubleClicked.connect(self._attach_read)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.state_label = QLabel(t("process.loading"), self)
        self.state_label.setWordWrap(True)
        layout.addWidget(self.state_label)
        warning = QLabel(t("process.write_warning"), self)
        warning.setProperty("tone", "warning")
        warning.setWordWrap(True)
        layout.addWidget(warning)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.read_button = QPushButton(t("process.attach_read"), self)
        self.read_button.setAccessibleName(t("process.attach_read"))
        self.read_button.clicked.connect(self._attach_read)
        self.write_button = QPushButton(t("process.attach_write"), self)
        self.write_button.setAccessibleName(t("process.attach_write"))
        self.write_button.setProperty("primary", True)
        self.write_button.clicked.connect(self._attach_write)
        cancel = QPushButton(t("action.cancel"), self)
        cancel.setAccessibleName(t("action.cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.read_button)
        buttons.addWidget(self.write_button)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self._selection_changed()
        QWidget.setTabOrder(self.search_edit, self.system_check)
        QWidget.setTabOrder(self.system_check, self.refresh_button)
        QWidget.setTabOrder(self.refresh_button, self.table)
        QWidget.setTabOrder(self.table, self.read_button)
        QWidget.setTabOrder(self.read_button, self.write_button)
        QWidget.setTabOrder(self.write_button, cancel)

    @Slot()
    def refresh(self) -> None:
        self.state_label.setText(t("process.loading"))
        self.refresh_button.setEnabled(False)
        self._controller.request_processes("", self.system_check.isChecked())

    @Slot(str)
    def _filter(self, query: str) -> None:
        self.proxy_model.set_query(query)
        self._update_empty_state()

    @Slot(object)
    def _on_processes(self, entries: object) -> None:
        if not isinstance(entries, list):
            return
        typed = [entry for entry in entries if isinstance(entry, ProcessEntry)]
        self.source_model.replace(typed)
        self.refresh_button.setEnabled(True)
        self._update_empty_state()
        if self.proxy_model.rowCount() > 0:
            self.table.selectRow(0)

    @Slot(str)
    def _on_failure(self, message: str) -> None:
        self.refresh_button.setEnabled(True)
        self.state_label.setText(message)
        self.state_label.setProperty("tone", "error")

    @Slot()
    def _selection_changed(self) -> None:
        entry = self.selected_entry()
        enabled = entry is not None and entry.can_attach
        self.read_button.setEnabled(enabled)
        self.write_button.setEnabled(enabled)

    def selected_entry(self) -> ProcessEntry | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        source_index = self.proxy_model.mapToSource(rows[0])
        return self.source_model.entry_at(source_index.row())

    @Slot(QModelIndex)
    @Slot()
    def _attach_read(self, _index: QModelIndex | None = None) -> None:
        self._attach(False)

    @Slot()
    def _attach_write(self) -> None:
        self._attach(True)

    def _attach(self, write_access: bool) -> None:
        entry = self.selected_entry()
        if entry is None or not entry.can_attach:
            return
        try:
            self.identity = self._controller.attach(entry.pid, write_access, Actor.USER)
        except Exception as exc:
            ErrorDialog(exc, self).exec()
            return
        self.write_access = write_access
        self.accept()

    def _update_empty_state(self) -> None:
        count = self.proxy_model.rowCount()
        self.state_label.setText("" if count else t("process.empty"))
        self.state_label.setVisible(count == 0)
