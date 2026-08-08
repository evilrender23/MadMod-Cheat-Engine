"""Focused Qt tests for the bundled Memory Lab process."""

from __future__ import annotations

import ctypes
import runpy
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from mempilot.core.data_types import format_hex
from mempilot.lab.memory_lab_app import LabState, MemoryLabWindow


@pytest.mark.gui
def test_lab_state_keeps_exact_ctypes_allocations_and_addresses() -> None:
    state = LabState()
    allocations = (
        state.health,
        state.coins,
        state.speed,
        state.stamina,
        state.alive,
        state.player_name,
        state.player_tag,
        state.marker,
    )
    addresses = state.addresses()

    assert state.health.value == 100
    assert state.coins.value == 500
    assert state.speed.value == 1.0
    assert state.stamina.value == 75.0
    assert state.alive.value is True
    assert state.player_name.value == "PlayerOne"
    assert state.player_tag.value == b"MEMPILOT-LAB"
    assert bytes(state.marker) == bytes.fromhex("4D454D50DEADBEEF1122334455667788")

    state.health.value = 321
    state.player_name.value = "Cambio externo"
    state.restore()

    current_allocations = (
        state.health,
        state.coins,
        state.speed,
        state.stamina,
        state.alive,
        state.player_name,
        state.player_tag,
        state.marker,
    )
    assert all(
        original is current
        for original, current in zip(allocations, current_allocations, strict=True)
    )
    assert state.addresses() == addresses
    assert addresses["health"] == ctypes.addressof(state.health)


@pytest.mark.gui
def test_window_buttons_use_live_memory_and_refresh_external_changes(qtbot: QtBot) -> None:
    state = LabState()
    window = MemoryLabWindow(state)
    qtbot.addWidget(window)
    window.show()

    state.health.value = 250
    qtbot.mouseClick(window.buttons["damage"], Qt.MouseButton.LeftButton)
    assert state.health.value == 223

    state.player_name.value = "Editado fuera"
    qtbot.waitUntil(
        lambda: window.table.item(5, 2).text() == "Editado fuera",
        timeout=1_000,
    )
    assert window.table.item(0, 3).text() == format_hex(ctypes.addressof(state.health))

    state.stamina.value = 1.0
    qtbot.mouseClick(
        window.auto_stamina,
        Qt.MouseButton.LeftButton,
        pos=QPoint(7, window.auto_stamina.height() // 2),
    )
    qtbot.waitUntil(lambda: state.stamina.value < 1.0, timeout=1_200)
    assert state.stamina.value >= 0.0


@pytest.mark.gui
def test_launcher_reuses_qapplication_and_opens_window(qtbot: QtBot) -> None:
    app = QApplication.instance()
    assert app is not None
    before = set(QApplication.topLevelWidgets())
    launcher = Path(__file__).resolve().parents[2] / "tools" / "memory_lab.py"

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(launcher), run_name="__main__")

    assert exit_info.value.code == 0
    assert QApplication.instance() is app
    opened = [
        widget
        for widget in QApplication.topLevelWidgets()
        if widget not in before and isinstance(widget, MemoryLabWindow)
    ]
    assert len(opened) == 1
    assert opened[0].isVisible()
    opened[0].close()
    qtbot.wait(10)
