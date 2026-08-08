"""Qt table model for controller-managed memory watches."""

from __future__ import annotations

from enum import IntEnum

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from mempilot.controller import Actor, AppController
from mempilot.core.data_types import format_hex
from mempilot.core.watcher import WatchEntry
from mempilot.i18n import t
from mempilot.ui.theme import AMBER_TINT, monospace_font

_ROOT_INDEX = QModelIndex()


class WatchColumn(IntEnum):
    """Stable watch-table column indexes."""

    NAME = 0
    ADDRESS = 1
    DATA_TYPE = 2
    VALUE = 3
    DESIRED = 4
    FROZEN = 5
    INTERVAL = 6
    NOTES = 7


_HEADER_KEYS: tuple[str, ...] = (
    "watch.column.name",
    "watch.column.address",
    "watch.column.type",
    "watch.column.value",
    "watch.column.desired",
    "watch.column.frozen",
    "watch.column.interval",
    "watch.column.notes",
)
_EDITABLE_COLUMNS = frozenset(
    {
        WatchColumn.NAME,
        WatchColumn.VALUE,
        WatchColumn.DESIRED,
        WatchColumn.INTERVAL,
        WatchColumn.NOTES,
    }
)
_MONOSPACE_COLUMNS = frozenset({WatchColumn.ADDRESS, WatchColumn.VALUE, WatchColumn.DESIRED})


class WatchModel(QAbstractTableModel):
    """Present watches and route every edit through ``AppController``."""

    operation_failed = Signal(str)

    def __init__(self, controller: AppController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._entries: list[WatchEntry] = []
        self._live_values: dict[str, str] = {}
        self._fixed_font = monospace_font()
        controller.watches_changed.connect(self.refresh)
        controller.watch_values.connect(self._apply_values)
        self.refresh()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        """Return watch count for the root table."""
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        """Return the eight fixed columns for the root table."""
        return 0 if parent.isValid() else len(_HEADER_KEYS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object | None:
        """Return localized horizontal headings and one-based row numbers."""
        role = int(role)
        if role != int(Qt.ItemDataRole.DisplayRole):
            return None
        if orientation is Qt.Orientation.Horizontal and 0 <= section < len(_HEADER_KEYS):
            return t(_HEADER_KEYS[section])
        if orientation is Qt.Orientation.Vertical and 0 <= section < len(self._entries):
            return section + 1
        return None

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> object | None:
        """Return O(1) display, edit and styling data for a watch cell."""
        role = int(role)
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        entry = self._entries[index.row()]
        column = WatchColumn(index.column())

        if role == int(Qt.ItemDataRole.CheckStateRole) and column is WatchColumn.FROZEN:
            return Qt.CheckState.Checked if entry.frozen else Qt.CheckState.Unchecked
        if role == int(Qt.ItemDataRole.BackgroundRole) and entry.frozen:
            return AMBER_TINT
        if role == int(Qt.ItemDataRole.FontRole) and column in _MONOSPACE_COLUMNS:
            return self._fixed_font
        if role == int(Qt.ItemDataRole.ToolTipRole) and entry.last_error:
            return t("watch.tooltip.error", error=entry.last_error)
        if role == int(Qt.ItemDataRole.TextAlignmentRole) and column in {
            WatchColumn.FROZEN,
            WatchColumn.INTERVAL,
        }:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role not in {
            int(Qt.ItemDataRole.DisplayRole),
            int(Qt.ItemDataRole.EditRole),
        }:
            return None

        if column is WatchColumn.NAME:
            return entry.label
        if column is WatchColumn.ADDRESS:
            return self._address_text(entry)
        if column is WatchColumn.DATA_TYPE:
            return t(f"watch.type.{entry.data_type.value}")
        if column is WatchColumn.VALUE:
            return self._live_values.get(entry.id, entry.current_value)
        if column is WatchColumn.DESIRED:
            return entry.desired_value or ""
        if column is WatchColumn.FROZEN:
            return ""
        if column is WatchColumn.INTERVAL:
            return (
                entry.interval_ms
                if role == int(Qt.ItemDataRole.EditRole)
                else t("watch.interval_value", value=entry.interval_ms)
            )
        if column is WatchColumn.NOTES:
            return entry.notes
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        """Expose editable metadata and a user-checkable frozen state."""
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        column = WatchColumn(index.column())
        if column in _EDITABLE_COLUMNS:
            flags |= Qt.ItemFlag.ItemIsEditable
        if column is WatchColumn.FROZEN:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(
        self,
        index: QModelIndex | QPersistentModelIndex,
        value: object,
        role: int = int(Qt.ItemDataRole.EditRole),
    ) -> bool:
        """Validate a cell edit and dispatch the corresponding facade method."""
        role = int(role)
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return False
        entry = self._entries[index.row()]
        column = WatchColumn(index.column())
        try:
            if role == int(Qt.ItemDataRole.CheckStateRole) and column is WatchColumn.FROZEN:
                frozen = value in (
                    Qt.CheckState.Checked,
                    Qt.CheckState.Checked.value,
                )
                desired = entry.desired_value or self._live_values.get(
                    entry.id, entry.current_value
                )
                self._controller.set_freeze(
                    entry.id,
                    frozen,
                    desired or None,
                    entry.interval_ms,
                    Actor.USER,
                )
                return True
            if role != int(Qt.ItemDataRole.EditRole) or column not in _EDITABLE_COLUMNS:
                return False
            text = str(value)
            if column is WatchColumn.NAME:
                self._controller.update_watch(entry.id, label=text, actor=Actor.USER)
            elif column is WatchColumn.VALUE:
                self._controller.set_watch_value(entry.id, text, Actor.USER)
            elif column is WatchColumn.DESIRED:
                if entry.frozen:
                    self._controller.set_freeze(entry.id, True, text, entry.interval_ms, Actor.USER)
                else:
                    self._controller.update_watch(entry.id, desired_value=text, actor=Actor.USER)
            elif column is WatchColumn.INTERVAL:
                interval_ms = int(text)
                if entry.frozen:
                    self._controller.set_freeze(
                        entry.id,
                        True,
                        entry.desired_value,
                        interval_ms,
                        Actor.USER,
                    )
                else:
                    self._controller.update_watch(
                        entry.id, interval_ms=interval_ms, actor=Actor.USER
                    )
            elif column is WatchColumn.NOTES:
                self._controller.update_watch(entry.id, notes=text, actor=Actor.USER)
            return True
        except Exception as exc:
            self.operation_failed.emit(str(exc))
            return False

    def entry_at(self, row: int) -> WatchEntry | None:
        """Return the stable snapshot represented by ``row``."""
        if not 0 <= row < len(self._entries):
            return None
        return self._entries[row]

    @Slot()
    def refresh(self) -> None:
        """Reload stable watch snapshots after a structural controller signal."""
        entries = self._controller.list_watches()
        known_ids = {entry.id for entry in entries}
        self.beginResetModel()
        self._entries = entries
        self._live_values = {
            watch_id: value
            for watch_id, value in self._live_values.items()
            if watch_id in known_ids
        }
        self.endResetModel()

    @Slot(object)
    def _apply_values(self, raw_values: object) -> None:
        if not isinstance(raw_values, dict):
            return
        rows_by_id = {entry.id: row for row, entry in enumerate(self._entries)}
        for raw_id, raw_value in raw_values.items():
            if not isinstance(raw_id, str) or not isinstance(raw_value, str):
                continue
            row = rows_by_id.get(raw_id)
            if row is None:
                continue
            self._live_values[raw_id] = raw_value
            value_index = self.index(row, WatchColumn.VALUE)
            self.dataChanged.emit(
                value_index,
                value_index,
                [
                    int(Qt.ItemDataRole.DisplayRole),
                    int(Qt.ItemDataRole.EditRole),
                ],
            )

    @staticmethod
    def _address_text(entry: WatchEntry) -> str:
        if entry.address is not None:
            return format_hex(entry.address)
        if entry.chain is not None:
            return t(
                "watch.address.chain",
                module=entry.chain.module,
                offset=entry.chain.base_offset,
                count=len(entry.chain.offsets),
            )
        if entry.module is not None and entry.offset is not None:
            return t("watch.address.module", module=entry.module, offset=entry.offset)
        return t("watch.address.unresolved")
