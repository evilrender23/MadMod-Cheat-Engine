"""GUI contracts for watch actions, confirmations, and no-AI operation."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton
from pytestqt.qtbot import QtBot
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.config.settings import AISettings, Settings, UISettings
from mempilot.controller import AppController
from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.data_types import DataType
from mempilot.i18n import t
from mempilot.services.audit_service import AuditService
from mempilot.services.settings_service import SettingsService
from mempilot.ui.dialogs.confirm_dialog import ConfirmDialog
from mempilot.ui.main_window import MainWindow
from mempilot.ui.models.watch_model import WatchColumn

pytestmark = pytest.mark.gui


def _no_ai_window(tmp_path: Path, qtbot: QtBot) -> tuple[MainWindow, AppController]:
    identity = ProcessIdentity(4242, "target.exe", 10.0, "C:/target.exe", Architecture.X64)
    memory = bytearray(512)
    struct.pack_into("<i", memory, 32, 100)
    backend = FakeMemoryBackend([(0x1000, memory, 0x04)], identity)
    settings = Settings(
        ai=AISettings(enabled=False),
        ui=UISettings(results_page_size=10, results_refresh_ms=50, watch_refresh_ms=50),
    )
    controller = AppController(
        backend,
        audit_service=AuditService(tmp_path / "audit.jsonl"),
        settings=settings,
    )
    window = MainWindow(
        controller,
        settings,
        SettingsService(tmp_path / "settings.json"),
        orchestrator=None,
    )
    qtbot.addWidget(window)
    window.show()
    return window, controller


def _button(dialog: ConfirmDialog, accessible_name: str) -> QPushButton:
    for button in dialog.findChildren(QPushButton):
        if button.accessibleName() == accessible_name:
            return button
    raise AssertionError(f"Button {accessible_name!r} was not found")


def test_context_action_adds_watch_and_frozen_checkbox_toggles(
    tmp_path: Path, qtbot: QtBot
) -> None:
    window, controller = _no_ai_window(tmp_path, qtbot)
    window.scan_panel.value_edit.setText("100")
    with qtbot.waitSignal(controller.scan_finished, timeout=3_000):  # type: ignore[attr-defined]
        window.scan_panel.first_button.click()

    window.results_view.table.selectRow(0)
    assert window.results_view.add_watch_action.isEnabled()
    window.results_view.add_watch_action.trigger()
    assert len(controller.list_watches()) == 1
    assert window.watch_view.model.rowCount() == 1

    model = window.watch_view.model
    desired = model.index(0, int(WatchColumn.DESIRED))
    frozen = model.index(0, int(WatchColumn.FROZEN))
    assert model.setData(desired, "100", Qt.ItemDataRole.EditRole)
    assert model.setData(frozen, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert controller.list_watches()[0].frozen
    assert model.data(frozen, Qt.ItemDataRole.CheckStateRole) is Qt.CheckState.Checked

    assert model.setData(frozen, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    assert not controller.list_watches()[0].frozen
    window.close()


def test_confirm_dialog_accepts_and_rejects(qtbot: QtBot) -> None:
    accepted = ConfirmDialog(
        action="Escribir valor",
        address=0x1234,
        data_type=DataType.INT32,
        current_value="100",
        new_value="250",
        allow_remember=True,
    )
    qtbot.addWidget(accepted)
    accepted.show()
    qtbot.mouseClick(_button(accepted, t("confirm.accept")), Qt.MouseButton.LeftButton)
    assert accepted.result() == ConfirmDialog.DialogCode.Accepted

    rejected = ConfirmDialog(
        action="Escribir valor",
        address=0x1234,
        data_type=DataType.INT32,
        current_value="100",
        new_value="250",
        allow_remember=False,
    )
    qtbot.addWidget(rejected)
    rejected.show()
    assert not rejected.remember_check.isVisible()
    qtbot.mouseClick(_button(rejected, t("confirm.reject")), Qt.MouseButton.LeftButton)
    assert rejected.result() == ConfirmDialog.DialogCode.Rejected


def test_no_ai_card_does_not_disable_memory_workflow(tmp_path: Path, qtbot: QtBot) -> None:
    window, controller = _no_ai_window(tmp_path, qtbot)
    assert window.chat_panel.disabled_card.isVisible()
    window.scan_panel.value_edit.setText("100")
    assert window.scan_panel.first_button.isEnabled()
    with qtbot.waitSignal(controller.scan_finished, timeout=3_000):  # type: ignore[attr-defined]
        window.scan_panel.first_button.click()
    assert window.results_view.model.rowCount() == 1
    assert window.watch_view.add_address_button.isEnabled()
    window.close()
