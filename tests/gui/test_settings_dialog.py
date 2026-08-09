"""Focused GUI contracts for selecting authenticated AI CLIs."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from tests.fixtures.fake_backend import FakeMemoryBackend

import mempilot.ui.dialogs.settings_dialog as settings_dialog_module
import mempilot.ui.main_window as main_window_module
from mempilot.agent.providers import ScriptedProvider
from mempilot.app import create_app
from mempilot.branding import APP_NAME, ORGANIZATION_NAME
from mempilot.config.settings import AISettings, CLIBackend, Settings, UISettings
from mempilot.controller import AppController
from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.i18n import Language
from mempilot.services.settings_service import SettingsService
from mempilot.ui.dialogs.settings_dialog import SettingsDialog

pytestmark = pytest.mark.gui


def test_ai_settings_select_cli_and_persist_without_api_fields(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings_dialog_module,
        "find_cli_executable",
        lambda settings: f"C:/bin/{settings.provider.value}.exe",
    )
    service = SettingsService(tmp_path / "settings.json")
    dialog = SettingsDialog(
        Settings(ai=AISettings(provider=CLIBackend.CLAUDE, model="sonnet")),
        service,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.provider_combo.currentData() == "claude"
    assert dialog.model_edit.text() == "sonnet"
    assert "C:/bin/claude.exe" in dialog.cli_status.text()
    assert not hasattr(dialog, "base_url_edit")
    assert not hasattr(dialog, "retries_spin")

    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("en"))
    dialog.provider_combo.setCurrentIndex(dialog.provider_combo.findData("agy"))
    dialog.executable_edit.setText("C:/custom/agy.exe")
    dialog.model_edit.clear()
    dialog._save()

    loaded = service.load()
    assert loaded.schema_version == 2
    assert loaded.ai.provider is CLIBackend.ANTIGRAVITY
    assert loaded.ai.executable == "C:/custom/agy.exe"
    assert loaded.ui.language is Language.ENGLISH
    assert loaded.ai.model is None
    raw = service.path.read_text(encoding="utf-8")
    assert "api_key" not in raw
    assert "base_url" not in raw


def test_main_window_applies_integer_accepted_result_and_reopens_saved_ai_settings(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SettingsService(tmp_path / "settings.json")
    initial = Settings(ai=AISettings(provider=CLIBackend.CODEX))
    identity = ProcessIdentity(77, "target.exe", 1.0, None, Architecture.X64)
    controller = AppController(
        FakeMemoryBackend([(0x1000, bytearray(64), 0x04)], identity),
        settings=initial,
    )
    replacement_provider = ScriptedProvider([])

    class _AcceptedSettingsDialog:
        def __init__(
            self,
            settings: Settings,
            settings_service: SettingsService,
            _parent: object,
        ) -> None:
            self.settings = settings.model_copy(deep=True)
            self.settings.ai.provider = CLIBackend.ANTIGRAVITY
            self._service = settings_service

        def exec(self) -> int:
            self._service.save(self.settings)
            return 1

    monkeypatch.setattr(main_window_module, "SettingsDialog", _AcceptedSettingsDialog)
    monkeypatch.setattr(
        main_window_module,
        "create_cli_provider",
        lambda _settings: replacement_provider,
    )
    app, window = create_app(
        [],
        controller=controller,
        settings=initial,
        settings_service=service,
        provider=ScriptedProvider([]),
    )
    qtbot.addWidget(window)
    window.show()
    assert app.applicationName() == APP_NAME
    assert app.organizationName() == ORGANIZATION_NAME
    assert not app.windowIcon().isNull()

    window.open_settings()

    assert window.settings.ai.provider is CLIBackend.ANTIGRAVITY
    assert service.load().ai.provider is CLIBackend.ANTIGRAVITY
    assert window.orchestrator is not None
    assert window.orchestrator.provider is replacement_provider
    window.close()


def test_create_app_builds_main_window_in_persisted_english(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    settings = Settings(
        ai=AISettings(enabled=False),
        ui=UISettings(language=Language.ENGLISH),
    )
    identity = ProcessIdentity(88, "target.exe", 2.0, None, Architecture.X64)
    controller = AppController(
        FakeMemoryBackend([(0x1000, bytearray(64), 0x04)], identity),
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

    assert window.top_bar.attach_button.text() == "Select process…"
    assert window.top_bar.settings_button.text() == "Settings"
    assert window.scan_panel.first_button.text() == "First scan"
    assert window.chat_panel.send_button.text() == "Send"
    window.close()
