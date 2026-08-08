"""Cross-module GUI contracts for the main application window."""

from __future__ import annotations

import struct
import time
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from tests.fixtures.fake_backend import FakeMemoryBackend
from tests.integration._target import TargetProcess

from mempilot.config.settings import ScanSettings, Settings, UISettings
from mempilot.controller import AppController
from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.services.audit_service import AuditService
from mempilot.services.settings_service import SettingsService
from mempilot.ui.dialogs.attach_dialog import AttachDialog
from mempilot.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


class _SlowFakeMemoryBackend(FakeMemoryBackend):
    """Delay each scanner read enough to exercise cancellation in the event loop."""

    def __init__(
        self,
        regions: list[tuple[int, bytearray, int]],
        identity: ProcessIdentity,
        delay_s: float,
    ) -> None:
        super().__init__(regions, identity)
        self.delay_s = delay_s

    def read_into(self, address: int, buffer: memoryview) -> int:
        if self.delay_s:
            time.sleep(self.delay_s)
        return super().read_into(address, buffer)


def _window(
    tmp_path: Path, qtbot: QtBot, *, slow: bool = False
) -> tuple[MainWindow, AppController, FakeMemoryBackend]:
    identity = ProcessIdentity(4242, "target.exe", 10.0, "C:/target.exe", Architecture.X64)
    memory = bytearray(16 << 10)
    struct.pack_into("<i", memory, 32, 100)
    struct.pack_into("<i", memory, 96, 100)
    backend: FakeMemoryBackend
    if slow:
        backend = _SlowFakeMemoryBackend([(0x1000, memory, 0x04)], identity, 0.01)
    else:
        backend = FakeMemoryBackend([(0x1000, memory, 0x04)], identity)
    settings = Settings(
        scan=ScanSettings(chunk_size=64),
        ui=UISettings(results_page_size=1, results_refresh_ms=50, watch_refresh_ms=50),
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
    )
    qtbot.addWidget(window)
    window.show()
    return window, controller, backend


def test_window_opens_and_process_selector_lists_child(tmp_path: Path, qtbot: QtBot) -> None:
    target = TargetProcess.start()
    window, controller, _backend = _window(tmp_path, qtbot)
    dialog = AttachDialog(controller, parent=window)
    qtbot.addWidget(dialog)
    dialog.show()

    try:
        assert window.isVisible()
        qtbot.waitUntil(dialog.refresh_button.isEnabled, timeout=10_000)
        entries = [
            dialog.source_model.entry_at(row) for row in range(dialog.source_model.rowCount())
        ]
        assert any(entry is not None and entry.pid == target.pid for entry in entries)
    finally:
        dialog.close()
        window.close()
        target.close()


def test_f5_progress_escape_cancel_and_results_population(tmp_path: Path, qtbot: QtBot) -> None:
    window, controller, backend = _window(tmp_path, qtbot, slow=True)
    window.scan_panel.value_edit.setText("100")
    assert window.global_actions["first_scan"].shortcut().toString() == "F5"
    with qtbot.waitSignal(controller.scan_started, timeout=3_000):  # type: ignore[attr-defined]
        window.global_actions["first_scan"].trigger()
    qtbot.wait(50)
    assert window.status_strip.progress_bar.isVisible()
    assert window.status_strip.cancel_button.isVisible()
    assert window.isEnabled()

    assert window.global_actions["cancel_scan"].shortcut().toString() == "Esc"
    with qtbot.waitSignal(controller.scan_cancelled, timeout=5_000):  # type: ignore[attr-defined]
        window.global_actions["cancel_scan"].trigger()
    qtbot.waitUntil(lambda: controller._scan_thread is None, timeout=5_000)
    assert not window.status_strip.progress_bar.isVisible()

    assert isinstance(backend, _SlowFakeMemoryBackend)
    backend.delay_s = 0.0
    with qtbot.waitSignal(controller.scan_finished, timeout=5_000):  # type: ignore[attr-defined]
        window.scan_panel.first_button.click()
    assert window.results_view.model.rowCount() == 1
    assert window.results_view.model.total == 2
    assert window.results_view.table.isVisible()

    window.results_view.model.next_page()
    assert window.results_view.model.offset == 1
    window.reset_scan()
    assert controller.scan_status().session_id is None
    assert window.results_view.model.rowCount() == 0
    window.close()


def test_close_invokes_controller_shutdown(
    tmp_path: Path, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, controller, _backend = _window(tmp_path, qtbot)
    called = False
    original = controller.shutdown

    def shutdown() -> None:
        nonlocal called
        called = True
        original()

    monkeypatch.setattr(controller, "shutdown", shutdown)
    window.close()
    assert called
