"""GUI contracts for the process-bound global-hotkey overlay."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog
from pytestqt.qtbot import QtBot
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.agent.orchestrator import AgentOrchestrator, ConfirmationRequest
from mempilot.agent.policies import AgentPolicy
from mempilot.agent.providers import ScriptedProvider
from mempilot.agent.tools import ToolRegistry
from mempilot.config.settings import AISettings, Settings, UISettings
from mempilot.controller import Actor, AppController
from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.data_types import DataType, decode_value
from mempilot.core.watcher import WatchSpec
from mempilot.i18n import t
from mempilot.services.audit_service import AuditService
from mempilot.services.settings_service import SettingsService
from mempilot.services.trainer_service import TrainerService, TrickMode
from mempilot.ui.dialogs.confirm_dialog import ConfirmDialog
from mempilot.ui.dialogs.trainer_dialog import TrainerDialog
from mempilot.ui.main_window import MainWindow

pytestmark = pytest.mark.gui


def _window(
    tmp_path: Path,
    qtbot: QtBot,
    *,
    with_agent: bool = False,
) -> tuple[MainWindow, AppController, FakeMemoryBackend, ProcessIdentity]:
    identity = ProcessIdentity(4242, "target.exe", 10.0, "C:/target.exe", Architecture.X64)
    memory = bytearray(512)
    struct.pack_into("<i", memory, 32, 100)
    backend = FakeMemoryBackend([(0x1000, memory, 0x04)], identity)
    settings = Settings(
        ai=AISettings(enabled=with_agent),
        ui=UISettings(results_page_size=10, results_refresh_ms=50, watch_refresh_ms=50),
    )
    controller = AppController(
        backend,
        audit_service=AuditService(tmp_path / "audit.jsonl"),
        trainer_service=TrainerService(tmp_path / "trainers"),
        settings=settings,
    )
    orchestrator = None
    if with_agent:
        policy = AgentPolicy()
        orchestrator = AgentOrchestrator(
            controller,
            ToolRegistry(controller, policy),
            policy,
            ScriptedProvider([]),
            settings.ai,
        )
    window = MainWindow(
        controller,
        settings,
        SettingsService(tmp_path / "settings.json"),
        orchestrator=orchestrator,
    )
    qtbot.addWidget(window)
    window.show()
    return window, controller, backend, identity


def test_overlay_opens_only_for_exact_foreground_process(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, _controller, _backend, identity = _window(tmp_path, qtbot)
    foreground_pid = identity.pid + 1
    monkeypatch.setattr(window._hotkeys, "foreground_pid", lambda: foreground_pid)

    window.toggle_overlay()
    assert not window.overlay.isVisible()

    foreground_pid = identity.pid
    window.toggle_overlay()
    assert window.overlay.isVisible()
    assert window.overlay.bound_identity == identity
    assert str(identity.pid) in window.overlay.process_label.text()

    foreground_pid = identity.pid + 1
    window.toggle_overlay()
    assert not window.overlay.isVisible()
    window.close()


def test_overlay_manual_write_freeze_and_read_only_guard(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, controller, backend, identity = _window(tmp_path, qtbot)
    watch = controller.add_watch(
        WatchSpec("Health", DataType.INT32, address=0x1020),
        Actor.USER,
    )
    window._last_write_access = True
    monkeypatch.setattr(window._hotkeys, "foreground_pid", lambda: identity.pid)
    monkeypatch.setattr(
        ConfirmDialog,
        "exec",
        lambda _dialog: QDialog.DialogCode.Accepted,
    )
    window.toggle_overlay()

    assert window.overlay.watch_combo.currentData() == watch.id
    window.overlay.value_edit.setText("250")
    qtbot.mouseClick(window.overlay.write_button, Qt.MouseButton.LeftButton)
    raw = bytearray(4)
    assert backend.read_into(0x1020, memoryview(raw)) == 4
    assert decode_value(DataType.INT32, bytes(raw)) == "250"
    assert window.overlay.operation_status.text() == t("overlay.write_ok")

    window.overlay.value_edit.setText("100")
    qtbot.mouseClick(window.overlay.freeze_button, Qt.MouseButton.LeftButton)
    assert controller.list_watches()[0].frozen
    assert controller.list_watches()[0].desired_value == "100"
    assert window.overlay.operation_status.text() == t("overlay.freeze_ok")
    qtbot.mouseClick(window.overlay.freeze_button, Qt.MouseButton.LeftButton)
    assert not controller.list_watches()[0].frozen
    assert window.overlay.operation_status.text() == t("overlay.unfreeze_ok")

    window._last_write_access = False
    window._overlay_write_watch(watch.id, "300")
    assert backend.read_into(0x1020, memoryview(raw)) == 4
    assert decode_value(DataType.INT32, bytes(raw)) == "250"
    assert window.overlay.operation_status.text() == t("overlay.read_only")
    window.close()


def test_overlay_saved_trick_activates_and_deactivates_reversibly(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, controller, _backend, identity = _window(tmp_path, qtbot)
    watch = controller.add_watch(
        WatchSpec("Health", DataType.INT32, address=0x1020, interval_ms=50),
        Actor.USER,
    )
    trick = controller.save_trainer_trick(
        watch.id,
        name="Vida infinita",
        enabled_value="100",
        disabled_value=None,
        mode=TrickMode.FREEZE,
        interval_ms=50,
        notes="Probado por el usuario.",
        actor=Actor.USER,
    )
    window._last_write_access = True
    monkeypatch.setattr(window._hotkeys, "foreground_pid", lambda: identity.pid)
    monkeypatch.setattr(
        ConfirmDialog,
        "exec",
        lambda _dialog: QDialog.DialogCode.Accepted,
    )
    window.toggle_overlay()

    assert window.overlay.trainer_combo.currentData() == trick.id
    assert t("overlay.trainer.active") in window.overlay.trainer_info.text()
    qtbot.mouseClick(window.overlay.trainer_toggle_button, Qt.MouseButton.LeftButton)
    assert controller.list_trainer_tricks()[0].active is False
    assert controller.list_watches()[0].frozen is False
    assert window.overlay.operation_status.text() == t("overlay.trainer.deactivated")

    qtbot.mouseClick(window.overlay.trainer_toggle_button, Qt.MouseButton.LeftButton)
    assert controller.list_trainer_tricks()[0].active is True
    assert controller.list_watches()[0].frozen is True
    assert window.overlay.operation_status.text() == t("overlay.trainer.activated")

    window._last_write_access = False
    window.overlay.show_for_process(identity, False, controller.list_watches())
    assert not window.overlay.trainer_toggle_button.isEnabled()
    window.close()


def test_overlay_edits_persisted_trainer_values_used_by_next_activation(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, controller, backend, identity = _window(tmp_path, qtbot)
    watch = controller.add_watch(
        WatchSpec("Damage", DataType.INT32, address=0x1020),
        Actor.USER,
    )
    trick = controller.save_trainer_trick(
        watch.id,
        name="Daño configurable",
        enabled_value="100",
        disabled_value="25",
        mode=TrickMode.WRITE_PAIR,
        interval_ms=100,
        notes="",
        actor=Actor.USER,
    )
    controller.set_trainer_trick_active(trick.id, False, Actor.USER)
    window._last_write_access = True
    monkeypatch.setattr(window._hotkeys, "foreground_pid", lambda: identity.pid)
    monkeypatch.setattr(
        ConfirmDialog,
        "exec",
        lambda _dialog: QDialog.DialogCode.Accepted,
    )
    window.toggle_overlay()

    assert window.overlay.trainer_enabled_edit.text() == "100"
    assert window.overlay.trainer_disabled_edit.text() == "25"
    window.overlay.trainer_enabled_edit.setText("300")
    window.overlay.trainer_disabled_edit.setText("50")
    qtbot.mouseClick(
        window.overlay.trainer_save_values_button,
        Qt.MouseButton.LeftButton,
    )

    persisted = controller.list_trainer_tricks()[0].trick
    assert persisted.enabled_value == "300"
    assert persisted.disabled_value == "50"
    qtbot.mouseClick(window.overlay.trainer_toggle_button, Qt.MouseButton.LeftButton)
    assert decode_value(DataType.INT32, backend.read(0x1020, 4)) == "300"
    qtbot.mouseClick(window.overlay.trainer_toggle_button, Qt.MouseButton.LeftButton)
    assert decode_value(DataType.INT32, backend.read(0x1020, 4)) == "50"
    window.close()


def test_overlay_creates_manual_trainer_with_user_values_without_ai(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, controller, backend, identity = _window(tmp_path, qtbot)
    watch = controller.add_watch(
        WatchSpec("Health", DataType.INT32, address=0x1020),
        Actor.USER,
    )
    window._last_write_access = True
    monkeypatch.setattr(window._hotkeys, "foreground_pid", lambda: identity.pid)

    def accept_manual(dialog: TrainerDialog) -> QDialog.DialogCode:
        dialog.name_edit.setText("Vida elegida por mí")
        dialog.enabled_edit.setText("250")
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData(TrickMode.WRITE_PAIR.value))
        dialog.disabled_edit.setText("73")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(TrainerDialog, "exec", accept_manual)
    monkeypatch.setattr(
        ConfirmDialog,
        "exec",
        lambda _dialog: QDialog.DialogCode.Accepted,
    )
    window.toggle_overlay()
    window.overlay.watch_combo.setCurrentIndex(window.overlay.watch_combo.findData(watch.id))
    qtbot.mouseClick(window.overlay.create_trainer_button, Qt.MouseButton.LeftButton)

    state = controller.list_trainer_tricks()[0]
    assert state.trick.name == "Vida elegida por mí"
    assert state.trick.enabled_value == "250"
    assert state.trick.disabled_value == "73"
    assert state.active
    assert decode_value(DataType.INT32, backend.read(0x1020, 4)) == "250"
    assert window.orchestrator is None
    window.close()


def test_overlay_replays_shared_conversation_and_routes_confirmation(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, _controller, _backend, identity = _window(tmp_path, qtbot, with_agent=True)
    assert window.orchestrator is not None
    window.orchestrator.conversation.add_user("Estado de salud")
    monkeypatch.setattr(window._hotkeys, "foreground_pid", lambda: identity.pid)
    window.toggle_overlay()

    assert "Estado de salud" in window.overlay.history.toPlainText()
    window.orchestrator.response_ready.emit("Salud estable")
    window.orchestrator.activity.emit("get_scan_status() → listo")
    assert "Salud estable" in window.overlay.history.toPlainText()
    assert "get_scan_status" in window.overlay.activity_label.text()

    decisions: list[str] = []
    window.orchestrator.confirmation_requested.emit(
        ConfirmationRequest(
            "Escribir 250 en Health",
            lambda: decisions.append("confirmada"),
            lambda: decisions.append("rechazada"),
        )
    )
    assert window.overlay.confirmation_card.isVisible()
    qtbot.mouseClick(window.overlay.confirm_button, Qt.MouseButton.LeftButton)
    assert decisions == ["confirmada"]
    assert not window.overlay.confirmation_card.isVisible()
    window.close()
