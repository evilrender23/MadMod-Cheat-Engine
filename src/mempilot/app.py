"""Application factory for production startup and focused GUI tests."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from mempilot import __version__
from mempilot.agent.orchestrator import AgentOrchestrator
from mempilot.agent.policies import AgentMode, AgentPolicy
from mempilot.agent.providers import AIProvider, OpenAIResponsesProvider
from mempilot.agent.tools import ToolRegistry
from mempilot.config.paths import ensure_dirs
from mempilot.config.settings import Settings
from mempilot.controller import AppController
from mempilot.services.credentials import resolve_api_key
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
    agent_policy: AgentPolicy | None = None,
    provider: AIProvider | None = None,
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
    existing_policy = getattr(controller, "_agent_policy", None) if controller is not None else None
    policy = (
        agent_policy
        or (existing_policy if isinstance(existing_policy, AgentPolicy) else None)
        or AgentPolicy(write_limit=effective_settings.ai.autonomous_write_limit)
    )
    policy.write_limit = effective_settings.ai.autonomous_write_limit
    facade = controller or AppController(settings=effective_settings, agent_policy=policy)
    if controller is not None and existing_policy is not policy:
        facade._agent_policy = policy
    identity = facade.attached_identity()
    if identity is not None:
        policy.bound_identity = identity
    effective_provider = provider if effective_settings.ai.enabled else None
    if effective_provider is None and effective_settings.ai.enabled:
        try:
            api_key = resolve_api_key()
        except Exception:
            api_key = None
        if api_key:
            effective_provider = OpenAIResponsesProvider(api_key, effective_settings.ai)
    if effective_provider is None:
        policy.mode = AgentMode.OFF
    elif policy.mode is AgentMode.OFF:
        policy.mode = AgentMode.GUIDED
    registry = ToolRegistry(facade, policy)
    orchestrator = AgentOrchestrator(
        facade,
        registry,
        policy,
        effective_provider,
        effective_settings.ai,
        facade,
    )
    window = MainWindow(facade, effective_settings, service, orchestrator=orchestrator)
    return app, window
