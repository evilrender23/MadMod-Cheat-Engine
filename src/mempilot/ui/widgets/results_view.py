"""Paged scan-result table, filters, navigation, and result actions."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from mempilot.controller import AppController
from mempilot.core.data_types import DataType, format_hex, type_size
from mempilot.core.scan_session import CandidateRow
from mempilot.i18n import t
from mempilot.ui.models.results_model import ResultsModel
from mempilot.ui.theme import SPACE_2, SPACE_3


class ResultsView(QWidget):
    """Compose a bounded result table with explicit source-level pagination."""

    add_watch_requested = Signal(object)
    edit_value_requested = Signal(object)
    reinterpret_requested = Signal(object, object)
    error_raised = Signal(object)

    def __init__(
        self,
        controller: AppController,
        page_size: int = 1000,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("resultsView")
        self.setMinimumWidth(520)
        self.model = ResultsModel(controller, page_size, self)
        self._build_ui()
        self.model.page_changed.connect(self._on_page_changed)
        self.model.load_failed.connect(self.error_raised)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)

        filters = QHBoxLayout()
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText(t("results.filter"))
        self.filter_edit.setAccessibleName(t("results.filter"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        filters.addWidget(self.filter_edit, 1)

        self.module_combo = QComboBox(self)
        self.module_combo.setAccessibleName(t("results.module"))
        self.module_combo.addItem(t("results.module"), None)
        self.module_combo.currentIndexChanged.connect(self._apply_filter)
        filters.addWidget(self.module_combo)
        layout.addLayout(filters)

        self.table = QTableView(self)
        self.table.setObjectName("resultsTable")
        self.table.setAccessibleName(t("results.table_accessible"))
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(lambda _index: self._emit_edit())
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        header.sectionClicked.connect(self._sort_by_section)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column in range(5, 9):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel(t("results.empty"), self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        pagination = QHBoxLayout()
        self.previous_button = QPushButton("◀", self)
        self.previous_button.setAccessibleName(t("results.previous_page"))
        self.previous_button.clicked.connect(self.model.previous_page)
        pagination.addWidget(self.previous_button)
        self.range_label = QLabel(t("results.range_empty"), self)
        self.range_label.setAccessibleName(t("results.range_empty"))
        pagination.addWidget(self.range_label)
        self.next_button = QPushButton("▶", self)
        self.next_button.setAccessibleName(t("results.next_page"))
        self.next_button.clicked.connect(self.model.next_page)
        pagination.addWidget(self.next_button)
        pagination.addStretch(1)
        pagination.addWidget(QLabel(t("results.page_jump"), self))
        self.page_spin = QSpinBox(self)
        self.page_spin.setAccessibleName(t("results.page_jump"))
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.editingFinished.connect(self._jump_to_page)
        pagination.addWidget(self.page_spin)
        layout.addLayout(pagination)

        self._install_actions()
        QWidget.setTabOrder(self.filter_edit, self.module_combo)
        QWidget.setTabOrder(self.module_combo, self.table)
        QWidget.setTabOrder(self.table, self.previous_button)
        QWidget.setTabOrder(self.previous_button, self.next_button)
        QWidget.setTabOrder(self.next_button, self.page_spin)

    def _install_actions(self) -> None:
        self.add_watch_action = QAction(t("results.action.add_watch"), self)
        self.add_watch_action.setShortcut(QKeySequence("Ctrl+W"))
        self.add_watch_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.add_watch_action.triggered.connect(self._emit_add_watch)
        self.addAction(self.add_watch_action)

        self.edit_action = QAction(t("results.action.edit"), self)
        self.edit_action.setShortcut(QKeySequence("F2"))
        self.edit_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.edit_action.triggered.connect(self._emit_edit)
        self.addAction(self.edit_action)

        self.copy_address_action = QAction(t("results.action.copy_address"), self)
        self.copy_address_action.setShortcut(QKeySequence("Ctrl+C"))
        self.copy_address_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.copy_address_action.triggered.connect(self._copy_address)
        self.addAction(self.copy_address_action)

        self.copy_value_action = QAction(t("results.action.copy_value"), self)
        self.copy_value_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.copy_value_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.copy_value_action.triggered.connect(self._copy_value)
        self.addAction(self.copy_value_action)

        self.delete_action = QAction(t("results.action.delete"), self)
        self.delete_action.setShortcut(QKeySequence("Delete"))
        self.delete_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.delete_action.triggered.connect(self._remove_selected)
        self.addAction(self.delete_action)

    def set_modules(self, names: list[str]) -> None:
        """Replace the source module choices while preserving a valid selection."""
        current = self.module_combo.currentData()
        self.module_combo.blockSignals(True)
        self.module_combo.clear()
        self.module_combo.addItem(t("results.module"), None)
        for name in sorted(set(names), key=str.casefold):
            self.module_combo.addItem(name, name)
        index = self.module_combo.findData(current)
        self.module_combo.setCurrentIndex(index if index >= 0 else 0)
        self.module_combo.blockSignals(False)

    def reload(self, *, reset_offset: bool = False) -> None:
        self.model.reload(reset_offset=reset_offset)

    def clear(self) -> None:
        self.filter_edit.blockSignals(True)
        self.module_combo.blockSignals(True)
        self.filter_edit.clear()
        self.module_combo.setCurrentIndex(0)
        self.filter_edit.blockSignals(False)
        self.module_combo.blockSignals(False)
        self.model.clear()

    def restore_header(self, state: bytes | object) -> None:
        """Restore a QSettings QByteArray header state when available."""
        self.table.horizontalHeader().restoreState(state)  # type: ignore[arg-type]

    def header_state(self) -> object:
        return self.table.horizontalHeader().saveState()

    @Slot()
    def _apply_filter(self) -> None:
        module = self.module_combo.currentData()
        self.model.set_filter(self.filter_edit.text(), module if isinstance(module, str) else None)

    @Slot(int)
    def _sort_by_section(self, section: int) -> None:
        header = self.table.horizontalHeader()
        if section not in self.model.ORDER_COLUMNS:
            return
        if header.sortIndicatorSection() == section:
            order = (
                Qt.SortOrder.DescendingOrder
                if header.sortIndicatorOrder() is Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            order = Qt.SortOrder.AscendingOrder
        header.setSortIndicator(section, order)
        self.model.set_order(section, order is Qt.SortOrder.DescendingOrder)

    @Slot(int, int, int)
    def _on_page_changed(self, first: int, last: int, total: int) -> None:
        if total:
            text = t(
                "results.range",
                first=f"{first:,}".replace(",", "."),
                last=f"{last:,}".replace(",", "."),
                total=f"{total:,}".replace(",", "."),
            )
        else:
            text = t("results.range_empty")
        self.range_label.setText(text)
        self.range_label.setAccessibleName(text)
        self.previous_button.setEnabled(self.model.offset > 0)
        self.next_button.setEnabled(self.model.offset + self.model.page_size < total)
        page_count = max(1, (total + self.model.page_size - 1) // self.model.page_size)
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(page_count)
        self.page_spin.setValue(self.model.offset // self.model.page_size + 1)
        self.page_spin.blockSignals(False)
        self.empty_label.setText(
            t("results.no_matches")
            if not total and bool(self.filter_edit.text().strip())
            else t("results.empty")
        )
        self.empty_label.setVisible(not bool(self.model.rows))
        self.table.setVisible(bool(self.model.rows))

    @Slot()
    def _jump_to_page(self) -> None:
        self.model.go_to_page(self.page_spin.value())

    @Slot(QPoint)
    def _show_context_menu(self, position: QPoint) -> None:
        index = self.table.indexAt(position)
        if index.isValid():
            self.table.selectRow(index.row())
        row = self._selected_row()
        menu = QMenu(self)
        menu.addAction(self.add_watch_action)
        menu.addAction(self.edit_action)
        menu.addSeparator()
        menu.addAction(self.copy_address_action)
        menu.addAction(self.copy_value_action)
        reinterpret = menu.addMenu(t("results.action.reinterpret"))
        if row is not None:
            for data_type in self._compatible_types(row.data_type):
                action = reinterpret.addAction(t(f"data_type.{data_type.value}"))
                action.setEnabled(data_type is not row.data_type)
                action.triggered.connect(
                    lambda _checked=False, selected=data_type: self.reinterpret_requested.emit(
                        row, selected
                    )
                )
        label_action = menu.addAction(t("results.action.label"))
        label_action.triggered.connect(self._label_selected)
        menu.addSeparator()
        menu.addAction(self.delete_action)
        enabled = row is not None
        for action in (
            self.add_watch_action,
            self.edit_action,
            self.copy_address_action,
            self.copy_value_action,
            self.delete_action,
            label_action,
        ):
            action.setEnabled(enabled)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _selected_row(self) -> CandidateRow | None:
        selection = self.table.selectionModel().selectedRows()
        return self.model.row_at(selection[0].row()) if selection else None

    @Slot()
    def _emit_add_watch(self) -> None:
        row = self._selected_row()
        if row is not None:
            self.add_watch_requested.emit(row)

    @Slot()
    def _emit_edit(self) -> None:
        row = self._selected_row()
        if row is not None:
            self.edit_value_requested.emit(row)

    @Slot()
    def _copy_address(self) -> None:
        row = self._selected_row()
        if row is not None:
            QApplication.clipboard().setText(format_hex(row.address))

    @Slot()
    def _copy_value(self) -> None:
        row = self._selected_row()
        if row is not None:
            QApplication.clipboard().setText(row.current)

    @Slot()
    def _label_selected(self) -> None:
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            return
        label, accepted = QInputDialog.getText(
            self, t("results.label.title"), t("results.label.prompt")
        )
        if accepted:
            self.model.label_row(selection[0].row(), label)

    @Slot()
    def _remove_selected(self) -> None:
        selection = self.table.selectionModel().selectedRows()
        if selection:
            self.model.remove_row(selection[0].row())

    @staticmethod
    def _compatible_types(source: DataType) -> list[DataType]:
        try:
            size = type_size(source)
        except ValueError:
            return [source]
        compatible: list[DataType] = []
        for data_type in DataType:
            try:
                if type_size(data_type) == size:
                    compatible.append(data_type)
            except ValueError:
                continue
        return compatible
