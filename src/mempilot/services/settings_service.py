"""Load and persist validated application settings."""

from contextlib import suppress
from pathlib import Path

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
        """Load settings, backing up invalid content and returning safe defaults."""
        if not self._path.exists():
            return Settings()
        try:
            return Settings.model_validate_json(self._path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
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
