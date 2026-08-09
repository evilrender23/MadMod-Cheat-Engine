"""Focused GUI contracts for no-AI operation and autonomous consent."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialogButtonBox, QLabel
from pytestqt.qtbot import QtBot
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.agent.policies import AgentMode
from mempilot.app import create_app
from mempilot.config.settings import AISettings, Settings
from mempilot.controller import AppController
from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.i18n import t
from mempilot.services.audit_service import AuditService
from mempilot.services.settings_service import SettingsService
from mempilot.ui.widgets.chat_panel import AutonomousConsentDialog, ChatPanel

pytestmark = pytest.mark.gui


def test_no_ai_factory_keeps_manual_application_enabled(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    identity = ProcessIdentity(4242, "target.exe", 10.0, None, Architecture.X64)
    backend = FakeMemoryBackend([(0x1000, bytearray(128), 0x04)], identity)
    settings = Settings(ai=AISettings(enabled=True))
    controller = AppController(
        backend,
        audit_service=AuditService(tmp_path / "audit.jsonl"),
        settings=settings,
    )

    _app, window = create_app(
        [],
        controller=controller,
        settings=settings,
        settings_service=SettingsService(tmp_path / "settings.json"),
        no_ai=True,
    )
    qtbot.addWidget(window)
    window.show()

    assert window.orchestrator is not None
    assert window.orchestrator.policy.mode is AgentMode.OFF
    assert window.orchestrator.policy is controller._agent_policy
    assert window.chat_panel.disabled_card.isVisible()
    window.scan_panel.value_edit.setText("100")
    assert window.scan_panel.first_button.isEnabled()
    window.chat_panel.input_edit.setText("Consulta local")
    window.chat_panel.send_button.click()
    assert window.chat_panel.history[0] == ("user", "Consulta local")
    assert window.chat_panel.history[1][0] == "agent"
    window.close()


def test_trainer_creator_submits_guided_agent_prompt(qtbot: QtBot) -> None:
    panel = ChatPanel(ai_enabled=True)
    qtbot.addWidget(panel)
    panel.show()

    with qtbot.waitSignal(panel.message_submitted, timeout=1000) as submitted:
        panel.trainer_button.click()

    assert submitted.args == [t("chat.trainer_prompt")]
    assert panel.history[-1] == ("user", t("chat.trainer_prompt"))


def test_autonomous_dialog_requires_explicit_checked_consent(qtbot: QtBot) -> None:
    dialog = AutonomousConsentDialog("target.exe", 4242, 20)
    qtbot.addWidget(dialog)
    dialog.show()
    accept = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)

    assert not accept.isEnabled()
    visible_text = "\n".join(label.text() for label in dialog.findChildren(QLabel))
    assert "No puede cambiar de proceso ni ampliar permisos" in visible_text
    dialog.consent.setChecked(True)
    assert accept.isEnabled()
