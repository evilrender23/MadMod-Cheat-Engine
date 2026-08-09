"""Focused tests for versioned application settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from mempilot.config.settings import Settings
from mempilot.services.settings_service import SettingsService


def test_missing_settings_return_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"

    loaded = SettingsService(path).load()

    assert loaded == Settings()
    assert not path.exists()


def test_corrupt_settings_are_backed_up_and_replaced_by_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"schema_version": 1, "scan": ', encoding="utf-8")

    loaded = SettingsService(path).load()

    assert loaded == Settings()
    assert not path.exists()
    assert (tmp_path / "settings.json.bak").read_text(encoding="utf-8").startswith("{")


def test_unsupported_settings_version_is_backed_up(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"schema_version": 3}', encoding="utf-8")

    loaded = SettingsService(path).load()

    assert loaded == Settings()
    assert not path.exists()
    assert (tmp_path / "settings.json.bak").read_text(encoding="utf-8") == ('{"schema_version": 3}')


def test_v1_api_settings_migrate_to_codex_cli_without_losing_limits(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        '{"schema_version":1,"ai":{"enabled":true,"model":"gpt-4.1",'
        '"base_url":"https://example.invalid/v1","timeout_s":77.0,"max_retries":4,'
        '"autonomous_write_limit":9,"confirmation_timeout_s":44.0}}',
        encoding="utf-8",
    )

    loaded = SettingsService(path).load()

    assert loaded.schema_version == 2
    assert loaded.ai.provider.value == "codex"
    assert loaded.ai.executable is None
    assert loaded.ai.model is None
    assert loaded.ai.timeout_s == 77.0
    assert loaded.ai.autonomous_write_limit == 9
    persisted = path.read_text(encoding="utf-8")
    assert "base_url" not in persisted
    assert "max_retries" not in persisted
    assert '"provider": "codex"' in persisted


def test_settings_round_trip_never_serializes_credentials(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = Settings.model_validate(
        {"ai": {"provider": "claude", "model": "sonnet", "executable": "claude.exe"}}
    )

    service = SettingsService(path)
    service.save(settings)

    raw = path.read_text(encoding="utf-8")
    assert service.load() == settings
    assert "api_key" not in raw
    assert "sk-" not in raw
    assert not (tmp_path / "settings.json.tmp").exists()


def test_settings_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"unexpected": True})


def test_settings_model_cannot_accept_an_api_key() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"ai": {"api_key": "sk-settings-secret-123456789"}})
