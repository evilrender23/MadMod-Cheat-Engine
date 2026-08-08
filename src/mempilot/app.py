"""Application factory for production startup and focused GUI tests."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from mempilot import __version__
from mempilot.config.paths import ensure_dirs
from mempilot.config.settings import Settings
from mempilot.controller import AppController
from mempilot.services.settings_service import SettingsService
from mempilot.ui.main_window import MainWindow
from mempilot.ui.theme import apply_theme


def create_app(
    argv: list[str] | None = None,
    *,
    controller: AppController | None = None,
    settings: Settings | None = None,
    settings_service: SettingsService | None = None,
    no_ai: bool = False,
) -> tuple[QApplication, MainWindow]:
    """Create or reuse QApplication and return the fully wired main window."""
    ensure_dirs()
    service = settings_service or SettingsService()
    effective_settings = (settings or service.load()).model_copy(deep=True)
    if no_ai:
        effective_settings.ai.enabled = False
    existing = QApplication.instance()
    if existing is None:
        app = QApplication(argv if argv is not None else sys.argv)
    elif isinstance(existing, QApplication):
        app = existing
    else:
        raise RuntimeError("Existe una instancia Qt que no es QApplication.")
    app.setApplicationName("MemPilot")
    app.setApplicationDisplayName("MemPilot")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("MemPilot")
    app.setOrganizationDomain("mempilot.local")
    apply_theme(app)
    facade = controller or AppController(settings=effective_settings)
    window = MainWindow(facade, effective_settings, service)
    return app, window
