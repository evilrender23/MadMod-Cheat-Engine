"""Focused GUI contracts for selecting authenticated AI CLIs."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

import mempilot.ui.dialogs.settings_dialog as settings_dialog_module
from mempilot.config.settings import AISettings, CLIBackend, Settings
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

    dialog.provider_combo.setCurrentIndex(dialog.provider_combo.findData("agy"))
    dialog.executable_edit.setText("C:/custom/agy.exe")
    dialog.model_edit.clear()
    dialog._save()

    loaded = service.load()
    assert loaded.schema_version == 2
    assert loaded.ai.provider is CLIBackend.ANTIGRAVITY
    assert loaded.ai.executable == "C:/custom/agy.exe"
    assert loaded.ai.model is None
    raw = service.path.read_text(encoding="utf-8")
    assert "api_key" not in raw
    assert "base_url" not in raw
