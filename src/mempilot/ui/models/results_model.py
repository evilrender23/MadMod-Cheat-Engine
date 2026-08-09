"""Explicitly paginated scan-results model."""

from __future__ import annotations

from typing import ClassVar

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor

from mempilot.controller import AppController, ResultsPage
from mempilot.core.data_types import format_hex
from mempilot.core.scan_session import CandidateRow, FilterSpec, OrderSpec
from mempilot.i18n import t
from mempilot.ui.theme import DISABLED, ERROR, monospace_font

_ROOT_INDEX = QModelIndex()


class ResultsModel(QAbstractTableModel):
    """Hold one page from ScanSession and request all ordering/filtering at the source."""

    page_changed = Signal(int, int, int)
    load_failed = Signal(object)

    COLUMNS = (
        "results.column.address",
        "results.column.value",
        "results.column.previous",
        "results.column.type",
        "results.column.region",
        "results.column.protection",
        "results.column.changes",
        "results.column.read",
        "results.column.write",
    )
    ORDER_COLUMNS: ClassVar[dict[int, str]] = {
        0: "address",
        1: "value",
        4: "region",
        6: "change_rate",
    }

    def __init__(
        self,
        controller: AppController,
        page_size: int = 1000,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._page_size = max(1, page_size)
        self._offset = 0
        self._total = 0
        self._total_unfiltered = 0
        self._rows: list[CandidateRow] = []
        self._address_rows: dict[int, int] = {}
        self._order = OrderSpec()
        self._filter = FilterSpec()
        self._labels: dict[int, str] = {}
        self._mono = monospace_font()
        controller.result_values.connect(self.update_live_values)

    @property
    def rows(self) -> list[CandidateRow]:
        """Return the bounded current page for view actions."""
        return list(self._rows)

    @property
    def offset(self) -> int:
        return self._offset

    @property
    def page_size(self) -> int:
        return self._page_size

    @property
    def total(self) -> int:
        return self._total

    @property
    def total_unfiltered(self) -> int:
        return self._total_unfiltered

    def row_at(self, row: int) -> CandidateRow | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def clear(self) -> None:
        """Clear the visible page without touching the attached process."""
        self.beginResetModel()
        self._rows = []
        self._address_rows = {}
        self._offset = 0
        self._total = 0
        self._total_unfiltered = 0
        self.endResetModel()
        self._controller.set_visible_results(())
        self.page_changed.emit(0, 0, 0)

    def reload(self, *, reset_offset: bool = False) -> None:
        """Fetch one page through AppController and atomically replace visible rows."""
        if reset_offset:
            self._offset = 0
        try:
            page = self._controller.results_page(
                self._offset, self._page_size, self._order, self._filter
            )
        except Exception as exc:
            self.load_failed.emit(exc)
            return
        if self._offset and self._offset >= page.total:
            self._offset = max(0, ((page.total - 1) // self._page_size) * self._page_size)
            try:
                page = self._controller.results_page(
                    self._offset, self._page_size, self._order, self._filter
                )
            except Exception as exc:
                self.load_failed.emit(exc)
                return
        self._set_page(page)

    def set_filter(self, text: str, module: str | None = None) -> None:
        """Apply source-level text/module filtering and return to page one."""
        normalized_module = module if module else None
        self._filter = FilterSpec(text=text.strip(), module=normalized_module)
        self.reload(reset_offset=True)

    def set_order(self, column: int, descending: bool) -> None:
        """Set a supported source order; unsupported columns keep the prior order."""
        name = self.ORDER_COLUMNS.get(column)
        if name is None:
            return
        self._order = OrderSpec(column=name, descending=descending)
        self.reload(reset_offset=True)

    def next_page(self) -> None:
        if self._offset + self._page_size < self._total:
            self._offset += self._page_size
            self.reload()

    def previous_page(self) -> None:
        if self._offset > 0:
            self._offset = max(0, self._offset - self._page_size)
            self.reload()

    def go_to_page(self, page_number: int) -> None:
        page_number = max(1, page_number)
        target = (page_number - 1) * self._page_size
        if self._total:
            target = min(target, ((self._total - 1) // self._page_size) * self._page_size)
        self._offset = target
        self.reload()

    def label_row(self, row: int, label: str) -> None:
        candidate = self.row_at(row)
        if candidate is None:
            return
        if label.strip():
            self._labels[candidate.address] = label.strip()
        else:
            self._labels.pop(candidate.address, None)
        index = self.index(row, 4)
        self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.DisplayRole)])

    def remove_row(self, row: int) -> None:
        """Remove a candidate from this bounded presentation page."""
        if not 0 <= row < len(self._rows):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        self._rows.pop(row)
        self._address_rows = {item.address: idx for idx, item in enumerate(self._rows)}
        self.endRemoveRows()
        self._controller.set_visible_results(self._rows)

    def update_live_values(self, values: object) -> None:
        """Apply scheduler values without triggering per-row table relayouts."""
        if not isinstance(values, dict):
            return
        changed: list[int] = []
        for raw_address, raw_value in values.items():
            if not isinstance(raw_address, int):
                continue
            row_number = self._address_rows.get(raw_address)
            if row_number is None:
                continue
            value = str(raw_value)
            if self._rows[row_number].current == value:
                continue
            self._rows[row_number].current = value
            changed.append(row_number)
        if changed:
            left = self.index(min(changed), 1)
            right = self.index(max(changed), 1)
            self.dataChanged.emit(left, right, [int(Qt.ItemDataRole.DisplayRole)])

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        if role == int(Qt.ItemDataRole.DisplayRole):
            values = (
                format_hex(row.address),
                row.current,
                row.previous or "—",
                t(f"data_type.{row.data_type.value}"),
                self._labels.get(row.address, row.region),
                row.protection,
                f"{row.change_rate * 100:.1f}%",
                t("ui.yes") if row.readable else t("ui.no"),
                t("ui.yes") if row.writable else t("ui.no"),
            )
            return values[index.column()]
        if role == int(Qt.ItemDataRole.UserRole):
            return row
        if role == int(Qt.ItemDataRole.FontRole) and index.column() in {0, 1, 2}:
            return self._mono
        if role == int(Qt.ItemDataRole.TextAlignmentRole) and index.column() in {6, 7, 8}:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == int(Qt.ItemDataRole.ForegroundRole):
            if not row.readable:
                return QBrush(QColor(ERROR))
            if index.column() == 8 and not row.writable:
                return QBrush(QColor(DISABLED))
        if role == int(Qt.ItemDataRole.ToolTipRole):
            return f"{format_hex(row.address)} · {row.region} · {row.protection}"
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if (
            role == int(Qt.ItemDataRole.DisplayRole)
            and orientation is Qt.Orientation.Horizontal
            and 0 <= section < len(self.COLUMNS)
        ):
            return t(self.COLUMNS[section])
        return None

    def _set_page(self, page: ResultsPage) -> None:
        self.beginResetModel()
        self._rows = list(page.rows)
        self._address_rows = {row.address: index for index, row in enumerate(self._rows)}
        self._offset = page.offset
        self._total = page.total
        self._total_unfiltered = page.total_unfiltered
        self.endResetModel()
        self._controller.set_visible_results(self._rows)
        first = self._offset + 1 if self._rows else 0
        last = self._offset + len(self._rows)
        self.page_changed.emit(first, last, self._total)
