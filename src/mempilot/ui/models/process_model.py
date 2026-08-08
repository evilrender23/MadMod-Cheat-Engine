"""Qt models for the bounded process picker data set."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor

from mempilot.core.process_service import ProcessEntry
from mempilot.i18n import t
from mempilot.ui.theme import DISABLED

_ROOT_INDEX = QModelIndex()


class ProcessModel(QAbstractTableModel):
    """Read-only process rows with stable access to their domain entries."""

    COLUMNS = (
        "process.column.name",
        "process.column.pid",
        "process.column.arch",
        "process.column.user",
        "process.column.path",
        "process.column.note",
    )

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[ProcessEntry] = []

    def replace(self, entries: list[ProcessEntry]) -> None:
        """Replace the complete small process data set."""
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def entry_at(self, row: int) -> ProcessEntry | None:
        """Return the process represented by a source-model row."""
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        entry = self._entries[index.row()]
        if role == int(Qt.ItemDataRole.DisplayRole):
            values = (
                entry.name,
                str(entry.pid),
                entry.architecture.value,
                entry.username or "—",
                entry.path or "—",
                entry.note
                or (t("process.available") if entry.can_attach else t("process.unavailable")),
            )
            return values[index.column()]
        if role == int(Qt.ItemDataRole.UserRole):
            return entry
        if role == int(Qt.ItemDataRole.ForegroundRole) and not entry.can_attach:
            return QColor(DISABLED)
        if role == int(Qt.ItemDataRole.TextAlignmentRole) and index.column() == 1:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == int(Qt.ItemDataRole.ToolTipRole):
            return entry.path or entry.note or entry.name
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

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        entry = self._entries[index.row()]
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if not entry.can_attach:
            flags &= ~Qt.ItemFlag.ItemIsEnabled
        return flags


class ProcessFilterModel(QSortFilterProxyModel):
    """Name/PID filter and deterministic sorting for process rows."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setDynamicSortFilter(True)

    def set_query(self, query: str) -> None:
        """Update the process name or exact PID query."""
        self.setFilterFixedString(query.strip())

    def filterAcceptsRow(
        self, source_row: int, _source_parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        query = self.filterRegularExpression().pattern().strip().casefold()
        if not query:
            return True
        source = self.sourceModel()
        if not isinstance(source, ProcessModel):
            return False
        entry = source.entry_at(source_row)
        if entry is None:
            return False
        if query.isdecimal():
            return str(entry.pid) == query
        return query in entry.name.casefold()

    def lessThan(
        self,
        left: QModelIndex | QPersistentModelIndex,
        right: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        left_value = left.data(Qt.ItemDataRole.DisplayRole)
        right_value = right.data(Qt.ItemDataRole.DisplayRole)
        if left.column() == 1:
            try:
                return int(str(left_value)) < int(str(right_value))
            except ValueError:
                return False
        return str(left_value).casefold() < str(right_value).casefold()
