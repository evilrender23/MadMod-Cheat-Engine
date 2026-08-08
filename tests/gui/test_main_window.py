"""Focused GUI contracts for the Step 2.2 application shell."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.config.settings import Settings, UISettings
from mempilot.controller import AppController
from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.services.audit_service import AuditService
from mempilot.services.settings_service import SettingsService
from mempilot.ui.main_window import MainWindow
from mempilot.ui.widgets.chat_panel import ChatPanel

pytestmark = pytest.mark.gui


def _window(tmp_path: Path, qtbot: QtBot) -> tuple[MainWindow, AppController]:
    identity = ProcessIdentity(4242, "target.exe", 10.0, "C:/target.exe", Architecture.X64)
    memory = bytearray(512)
    struct.pack_into("<i", memory, 32, 100)
    struct.pack_into("<i", memory, 96, 100)
    backend = FakeMemoryBackend([(0x1000, memory, 0x04)], identity)
    settings = Settings(ui=UISettings(results_page_size=1, watch_refresh_ms=50))
    controller = AppController(
        backend,
        audit_service=AuditService(tmp_path / "audit.jsonl"),
        settings=settings,
    )
    window = MainWindow(
        controller,
        settings,
        SettingsService(tmp_path / "settings.json"),
    )
    qtbot.addWidget(window)
    window.show()
    return window, controller


def test_window_scans_pages_adds_watch_and_resets(tmp_path: Path, qtbot: QtBot) -> None:
    window, controller = _window(tmp_path, qtbot)
    window.scan_panel.value_edit.setText("100")
    with qtbot.waitSignal(controller.scan_finished, timeout=3000):  # type: ignore[attr-defined]
        window.scan_panel.first_button.click()
    assert window.results_view.model.rowCount() == 1
    assert window.results_view.model.total == 2
    window.results_view.table.selectRow(0)
    window.results_view.add_watch_action.trigger()
    assert len(controller.list_watches()) == 1
    window.results_view.model.next_page()
    assert window.results_view.model.offset == 1
    window.reset_scan()
    assert controller.scan_status().session_id is None
    assert window.results_view.model.rowCount() == 0
    window.close()


def test_chat_panel_no_ai_keeps_history_and_activity(qtbot: QtBot) -> None:
    panel = ChatPanel(ai_enabled=False)
    qtbot.addWidget(panel)
    panel.show()
    assert panel.disabled_card.isVisible()
    panel.add_activity("start_scan(int32, exact, 100) → 2 candidatos")
    panel.input_edit.setText("Encuentra la vida")
    panel.send_button.click()
    assert panel.activities == ("start_scan(int32, exact, 100) → 2 candidatos",)
    assert panel.history[0] == ("user", "Encuentra la vida")
    assert panel.history[1][0] == "agent"


def test_close_invokes_controller_shutdown(
    tmp_path: Path, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, controller = _window(tmp_path, qtbot)
    called = False
    original = controller.shutdown

    def shutdown() -> None:
        nonlocal called
        called = True
        original()

    monkeypatch.setattr(controller, "shutdown", shutdown)
    window.close()
    assert called
