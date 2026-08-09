"""Load and persist validated application settings."""

import json
from contextlib import suppress
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mempilot.config.paths import SETTINGS_FILE
from mempilot.config.settings import Settings
from mempilot.logging_setup import redact_secrets


class SettingsService:
    """Manage the versioned settings JSON document."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else SETTINGS_FILE

    @property
    def path(self) -> Path:
        """Return the settings file managed by this service."""
        return self._path

    def load(self) -> Settings:
        """Load, migrate, and validate settings, backing up invalid content."""
        if not self._path.exists():
            return Settings()
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
            migrated = _migrate_v1(document)
            settings = Settings.model_validate(migrated)
            if migrated is not document:
                self.save(settings)
            return settings
        except (OSError, ValidationError, ValueError, TypeError, json.JSONDecodeError):
            self._backup_invalid_file()
            return Settings()

    def save(self, settings: Settings) -> None:
        """Atomically persist validated settings without credential-shaped strings."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(f"{self._path.name}.tmp")
        try:
            serialized = redact_secrets(settings.model_dump_json(indent=2)) + "\n"
            temporary.write_text(serialized, encoding="utf-8")
            temporary.replace(self._path)
        finally:
            temporary.unlink(missing_ok=True)

    def _backup_invalid_file(self) -> None:
        backup = self._path.with_name(f"{self._path.name}.bak")
        with suppress(OSError):
            self._path.replace(backup)


def _migrate_v1(document: Any) -> Any:
    """Replace API connection fields with the Codex CLI defaults."""
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        return document
    migrated = dict(document)
    migrated["schema_version"] = 2
    raw_ai = migrated.get("ai")
    ai = dict(raw_ai) if isinstance(raw_ai, dict) else {}
    ai.pop("base_url", None)
    ai.pop("max_retries", None)
    ai["provider"] = "codex"
    ai["executable"] = None
    ai["model"] = None
    migrated["ai"] = ai
    return migrated
