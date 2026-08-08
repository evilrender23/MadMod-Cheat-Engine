"""PySide6 process used to demonstrate MemPilot memory operations."""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTime, QTimer, Slot
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mempilot.core.data_types import format_hex
from mempilot.i18n import t


@dataclass(frozen=True, slots=True)
class LabVariable:
    """A display snapshot of one stable ctypes allocation."""

    name: str
    data_type: str
    value: str
    address: int


class LabState:
    """Own stable ctypes allocations whose values can be edited externally."""

    _MARKER = (
        0x4D,
        0x45,
        0x4D,
        0x50,
        0xDE,
        0xAD,
        0xBE,
        0xEF,
        0x11,
        0x22,
        0x33,
        0x44,
        0x55,
        0x66,
        0x77,
        0x88,
    )

    def __init__(self) -> None:
        self.health = ctypes.c_int32(100)
        self.coins = ctypes.c_int32(500)
        self.speed = ctypes.c_float(1.0)
        self.stamina = ctypes.c_double(75.0)
        self.alive = ctypes.c_bool(True)
        self.player_name = ctypes.create_unicode_buffer("PlayerOne", 64)
        self.player_tag = ctypes.create_string_buffer(b"MEMPILOT-LAB", 32)
        self.marker = (ctypes.c_ubyte * 16)(*self._MARKER)

    def addresses(self) -> dict[str, int]:
        """Return the current addresses of the stable allocations."""
        return {
            "health": ctypes.addressof(self.health),
            "coins": ctypes.addressof(self.coins),
            "speed": ctypes.addressof(self.speed),
            "stamina": ctypes.addressof(self.stamina),
            "alive": ctypes.addressof(self.alive),
            "player_name": ctypes.addressof(self.player_name),
            "player_tag": ctypes.addressof(self.player_tag),
            "marker": ctypes.addressof(self.marker),
        }

    def snapshots(self) -> tuple[LabVariable, ...]:
        """Read every allocation and format it for the table."""
        addresses = self.addresses()
        return (
            LabVariable("health", "Int32", str(self.health.value), addresses["health"]),
            LabVariable("coins", "Int32", str(self.coins.value), addresses["coins"]),
            LabVariable("speed", "Float32", f"{self.speed.value:.2f}", addresses["speed"]),
            LabVariable("stamina", "Float64", f"{self.stamina.value:.2f}", addresses["stamina"]),
            LabVariable(
                "alive",
                "Bool",
                t("lab.value.true") if self.alive.value else t("lab.value.false"),
                addresses["alive"],
            ),
            LabVariable(
                "player_name", "Texto UTF-16 LE", self.player_name.value, addresses["player_name"]
            ),
            LabVariable(
                "player_tag",
                "Texto UTF-8",
                self.player_tag.value.decode("utf-8", errors="replace"),
                addresses["player_tag"],
            ),
            LabVariable(
                "marker",
                "AOB (16 bytes)",
                " ".join(f"{byte:02X}" for byte in self.marker),
                addresses["marker"],
            ),
        )

    def restore(self) -> None:
        """Restore values in place without replacing any ctypes allocation."""
        self.health.value = 100
        self.coins.value = 500
        self.speed.value = 1.0
        self.stamina.value = 75.0
        self.alive.value = True
        self.player_name.value = "PlayerOne"
        self.player_tag.value = b"MEMPILOT-LAB"
        for index, byte in enumerate(self._MARKER):
            self.marker[index] = byte


class MemoryLabWindow(QWidget):
    """Spanish desktop UI exposing the laboratory allocations and controls."""

    def __init__(self, state: LabState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state or LabState()
        self.setObjectName("memoryLabWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(t("lab.window_title", pid=os.getpid()))
        self.setMinimumSize(760, 600)
        self.resize(900, 680)
        self._apply_local_theme()

        layout = QVBoxLayout(self)
        title = QLabel(t("lab.window_title", pid=os.getpid()))
        title.setObjectName("labTitle")
        title_font = title.font()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        description = QLabel(t("lab.description"))
        description.setWordWrap(True)
        layout.addWidget(description)

        self.table = QTableWidget(0, 4, self)
        self.table.setObjectName("variablesTable")
        self.table.setAccessibleName(t("lab.table_accessible"))
        self.table.setHorizontalHeaderLabels(
            [
                t("lab.column.name"),
                t("lab.column.type"),
                t("lab.column.value"),
                t("lab.column.address"),
            ]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._set_monospace_columns()
        layout.addWidget(self.table, 1)

        controls = QGroupBox(t("lab.actions"), self)
        controls_layout = QGridLayout(controls)
        self.buttons: dict[str, QPushButton] = {}
        button_specs = (
            ("damage", "lab.damage", self._damage),
            ("heal", "lab.heal", self._heal),
            ("spend_coins", "lab.spend_coins", self._spend_coins),
            ("add_coins", "lab.add_coins", self._add_coins),
            ("speed_up", "lab.speed_up", self._speed_up),
            ("speed_down", "lab.speed_down", self._speed_down),
            ("toggle_alive", "lab.toggle_alive", self._toggle_alive),
            ("restore", "lab.restore", self._restore),
        )
        for index, (name, text_key, callback) in enumerate(button_specs):
            button = QPushButton(t(text_key), controls)
            button.setObjectName(f"{name}Button")
            button.setAccessibleName(t(text_key))
            button.clicked.connect(callback)
            controls_layout.addWidget(button, index // 2, index % 2)
            self.buttons[name] = button
        layout.addWidget(controls)

        self.auto_stamina = QCheckBox(t("lab.auto_stamina"), self)
        self.auto_stamina.setObjectName("autoStaminaCheckBox")
        self.auto_stamina.setAccessibleName(t("lab.auto_stamina"))
        self.auto_stamina.toggled.connect(self._toggle_auto_stamina)
        layout.addWidget(self.auto_stamina)

        log_label = QLabel(t("lab.log_label"), self)
        layout.addWidget(log_label)
        self.action_log = QPlainTextEdit(self)
        self.action_log.setObjectName("actionLog")
        self.action_log.setAccessibleName(t("lab.log_label"))
        self.action_log.setReadOnly(True)
        self.action_log.document().setMaximumBlockCount(200)
        layout.addWidget(self.action_log)

        self.stamina_timer = QTimer(self)
        self.stamina_timer.setInterval(500)
        self.stamina_timer.timeout.connect(self._decrease_stamina)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(200)
        self.refresh_timer.timeout.connect(self.refresh_table)
        self.refresh_table()
        self.refresh_timer.start()

    def _apply_local_theme(self) -> None:
        self.setStyleSheet(
            """
            QWidget#memoryLabWindow {
                background: #202225;
                color: #E6E8EB;
            }
            QLabel#labTitle { color: #5B9BD5; }
            QGroupBox {
                border: 1px solid #3A3D42;
                border-radius: 3px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
            QTableWidget, QPlainTextEdit {
                background: #17191C;
                alternate-background-color: #25282C;
                border: 1px solid #3A3D42;
                gridline-color: #34373C;
            }
            QHeaderView::section {
                background: #2B2E33;
                color: #E6E8EB;
                border: 0;
                border-right: 1px solid #3A3D42;
                border-bottom: 1px solid #3A3D42;
                padding: 5px;
            }
            QPushButton {
                background: #2B2E33;
                border: 1px solid #474B52;
                border-radius: 3px;
                min-height: 26px;
                padding: 2px 10px;
            }
            QPushButton:hover { border-color: #5B9BD5; }
            QPushButton:pressed { background: #3D6F9E; }
            QCheckBox { spacing: 7px; }
            """
        )

    def _set_monospace_columns(self) -> None:
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        if not mono.exactMatch():
            mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._monospace_font = mono

    @Slot()
    def refresh_table(self) -> None:
        """Re-read ctypes values so external writes become visible."""
        snapshots = self.state.snapshots()
        if self.table.rowCount() != len(snapshots):
            self.table.setRowCount(len(snapshots))
        for row, variable in enumerate(snapshots):
            values = (
                variable.name,
                variable.data_type,
                variable.value,
                format_hex(variable.address),
            )
            for column, value in enumerate(values):
                item = self.table.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    if column in (2, 3):
                        item.setFont(self._monospace_font)
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                        )
                    self.table.setItem(row, column, item)
                if item.text() != value:
                    item.setText(value)

    def _append_log(self, message: str) -> None:
        timestamp = QTime.currentTime().toString("HH:mm:ss")
        self.action_log.appendPlainText(f"[{timestamp}] {message}")

    @Slot()
    def _damage(self) -> None:
        self.state.health.value = max(0, self.state.health.value - 27)
        self._append_log(t("lab.log.damage", value=self.state.health.value))
        self.refresh_table()

    @Slot()
    def _heal(self) -> None:
        self.state.health.value = self.state.health.value + 15
        self._append_log(t("lab.log.heal", value=self.state.health.value))
        self.refresh_table()

    @Slot()
    def _spend_coins(self) -> None:
        self.state.coins.value = max(0, self.state.coins.value - 50)
        self._append_log(t("lab.log.spend_coins", value=self.state.coins.value))
        self.refresh_table()

    @Slot()
    def _add_coins(self) -> None:
        self.state.coins.value = self.state.coins.value + 100
        self._append_log(t("lab.log.add_coins", value=self.state.coins.value))
        self.refresh_table()

    @Slot()
    def _speed_up(self) -> None:
        self.state.speed.value = self.state.speed.value + 0.25
        self._append_log(t("lab.log.speed_up", value=f"{self.state.speed.value:.2f}"))
        self.refresh_table()

    @Slot()
    def _speed_down(self) -> None:
        self.state.speed.value = self.state.speed.value - 0.25
        self._append_log(t("lab.log.speed_down", value=f"{self.state.speed.value:.2f}"))
        self.refresh_table()

    @Slot()
    def _toggle_alive(self) -> None:
        self.state.alive.value = not self.state.alive.value
        value = t("lab.value.true") if self.state.alive.value else t("lab.value.false")
        self._append_log(t("lab.log.toggle_alive", value=value))
        self.refresh_table()

    @Slot()
    def _restore(self) -> None:
        self.state.restore()
        self._append_log(t("lab.log.restore"))
        self.refresh_table()

    @Slot(bool)
    def _toggle_auto_stamina(self, enabled: bool) -> None:
        if enabled:
            self.stamina_timer.start()
            message_key = "lab.log.auto_stamina_on"
        else:
            self.stamina_timer.stop()
            message_key = "lab.log.auto_stamina_off"
        self._append_log(t(message_key))

    @Slot()
    def _decrease_stamina(self) -> None:
        self.state.stamina.value = max(0.0, self.state.stamina.value - 0.7)
        self.refresh_table()


_OPEN_WINDOWS: set[MemoryLabWindow] = set()


def run_lab(argv: list[str] | None = None) -> int:
    """Show Memory Lab, reusing an existing QApplication when one is active."""
    instance = QApplication.instance()
    owns_application = instance is None
    if instance is None:
        app = QApplication(argv if argv is not None else sys.argv)
    elif isinstance(instance, QApplication):
        app = instance
    else:
        raise RuntimeError("Ya existe una aplicación Qt incompatible.")

    window = MemoryLabWindow()
    _OPEN_WINDOWS.add(window)
    window.destroyed.connect(lambda: _OPEN_WINDOWS.discard(window))
    window.show()
    if not owns_application:
        return 0

    exit_code = app.exec()
    _OPEN_WINDOWS.discard(window)
    return exit_code
