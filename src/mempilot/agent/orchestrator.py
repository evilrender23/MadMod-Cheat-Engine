"""Sequential agent workflow, policy decisions, and GUI-thread tool bridge."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from mempilot.agent.conversation import Conversation
from mempilot.agent.policies import AgentMode, AgentPolicy, Decision, FlowState
from mempilot.agent.prompts import SYSTEM_PROMPT, state_line
from mempilot.agent.providers import AIProvider
from mempilot.agent.tools import ToolDef, ToolRegistry
from mempilot.config.settings import AISettings
from mempilot.controller import AppController, ScanStatus
from mempilot.core.backend import ProcessIdentity
from mempilot.core.exceptions import MemPilotError, ProviderError
from mempilot.core.scan_session import ScanSession
from mempilot.core.watcher import WatchEntry
from mempilot.ui.workers import ToolInvocation

_MAX_TOOL_ROUNDS = 32


@dataclass(frozen=True, slots=True)
class FlowSnapshot:
    """Immutable controller state safe to inspect from the provider worker."""

    identity: ProcessIdentity | None
    write_access: bool
    state: FlowState
    scan: ScanStatus
    watches: tuple[WatchEntry, ...]


class FlowMachine:
    """Authoritative workflow derived from controller signals, never model memory."""

    def __init__(self, controller: AppController) -> None:
        self._controller = controller
        self._lock = threading.RLock()
        self.state = FlowState.NO_PROCESS
        self._identity = controller.attached_identity()
        self._write_access = False
        self._scan = controller.scan_status()
        self._watches = tuple(controller.list_watches())
        if self._identity is not None:
            self.state = FlowState.ATTACHED
        controller.attached.connect(self.on_attached)
        controller.detached.connect(self.on_detached)
        controller.process_lost.connect(self.on_process_lost)
        controller.scan_started.connect(self.on_scan_started)
        controller.scan_finished.connect(self.on_scan_finished)
        controller.watches_changed.connect(self.on_watches_changed)

    @Slot(object)
    def on_attached(self, raw_identity: object) -> None:
        if not isinstance(raw_identity, ProcessIdentity):
            return
        with self._lock:
            self._identity = raw_identity
            self._scan = self._controller.scan_status()
            self._watches = tuple(self._controller.list_watches())
            self.state = FlowState.ATTACHED

    @Slot(str)
    def on_detached(self, _reason: str) -> None:
        self._reset_process()

    @Slot(int)
    def on_process_lost(self, _pid: int) -> None:
        self._reset_process()

    @Slot(object)
    def on_scan_started(self, _request: object) -> None:
        with self._lock:
            self._scan = self._controller.scan_status()
            self.state = FlowState.SCANNING

    @Slot(object)
    def on_scan_finished(self, raw_session: object) -> None:
        if not isinstance(raw_session, ScanSession):
            return
        candidates = raw_session.total()
        with self._lock:
            self._scan = self._controller.scan_status()
            self.state = FlowState.NARROWED if candidates <= 5 else FlowState.CANDIDATES

    @Slot()
    def on_watches_changed(self) -> None:
        watches = tuple(self._controller.list_watches())
        with self._lock:
            self._watches = watches
            if watches:
                self.state = FlowState.WATCHING

    def note_write_access(self, enabled: bool) -> None:
        """Record access selected by the GUI or a successful attach tool call."""
        with self._lock:
            self._write_access = enabled

    def mark_awaiting_change(self) -> None:
        """Enter the user-action pause only from a broad candidate set."""
        with self._lock:
            if self.state is FlowState.CANDIDATES:
                self.state = FlowState.AWAITING_CHANGE

    def snapshot(self) -> FlowSnapshot:
        with self._lock:
            return FlowSnapshot(
                self._identity,
                self._write_access,
                self.state,
                self._scan,
                self._watches,
            )

    def _reset_process(self) -> None:
        with self._lock:
            self._identity = None
            self._write_access = False
            self._scan = self._controller.scan_status()
            self._watches = ()
            self.state = FlowState.NO_PROCESS


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """User-visible texts produced by one complete provider/tool loop."""

    texts: tuple[str, ...]


class AgentTurnJob:
    """One provider turn that may execute multiple sequential tool rounds."""

    def __init__(
        self,
        provider: AIProvider,
        registry: ToolRegistry,
        conversation: Conversation,
        flow: FlowMachine,
        policy: AgentPolicy,
        tool_timeout_s: float,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._conversation = conversation
        self._flow = flow
        self._policy = policy
        self._tool_timeout_s = tool_timeout_s

    def run(
        self,
        cancel: threading.Event,
        request_tool: Callable[[str, str, float | None], str],
    ) -> AgentRunResult:
        texts: list[str] = []
        for _round in range(_MAX_TOOL_ROUNDS):
            if cancel.is_set():
                return AgentRunResult(tuple(texts))
            snapshot = self._flow.snapshot()
            turn = self._provider.complete(
                SYSTEM_PROMPT,
                self._conversation.provider_input(
                    state_line(
                        snapshot.identity,
                        snapshot.write_access,
                        snapshot.state,
                        snapshot.scan,
                        snapshot.watches,
                        self._policy,
                    )
                ),
                self._registry.specs(),
            )
            self._conversation.add_provider_turn(turn)
            if turn.text.strip():
                texts.append(turn.text.strip())
            if not turn.tool_calls:
                if turn.text.strip():
                    self._flow.mark_awaiting_change()
                    return AgentRunResult(tuple(texts))
                raise ProviderError(
                    "El proveedor no devolvió texto ni herramientas. Inténtalo de nuevo."
                )
            for call in turn.tool_calls:
                if cancel.is_set():
                    return AgentRunResult(tuple(texts))
                result = request_tool(call.name, call.arguments_json, self._tool_timeout_s)
                self._conversation.add_tool_output(call, result)
        raise ProviderError(
            "El agente superó el límite de pasos consecutivos. "
            "Reformula la petición y continúa desde el estado actual."
        )


@dataclass(frozen=True, slots=True)
class ConfirmationRequest:
    """Inline confirmation callbacks owned and timed by AgentOrchestrator."""

    detail: str
    confirm: Callable[[], None]
    reject: Callable[[], None]


@dataclass(slots=True)
class _PendingConfirmation:
    invocation: ToolInvocation
    timer: QTimer


class AgentOrchestrator(QObject):
    """Own provider replay and make every tool decision on the GUI thread."""

    response_ready = Signal(str)
    activity = Signal(str)
    confirmation_requested = Signal(object)
    busy_changed = Signal(bool)
    mode_changed = Signal(str)

    def __init__(
        self,
        controller: AppController,
        registry: ToolRegistry,
        policy: AgentPolicy,
        provider: AIProvider | None,
        settings: AISettings,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.registry = registry
        self.policy = policy
        self.provider = provider
        self.settings = settings
        self.flow = FlowMachine(controller)
        self.conversation = Conversation()
        self._tools = {tool.name: tool for tool in registry.tools}
        self._pending: dict[int, _PendingConfirmation] = {}
        self._busy = False
        self._autonomous_identity: ProcessIdentity | None = None
        if provider is None:
            self.policy.mode = AgentMode.OFF
        controller.agent_event.connect(self._on_agent_event)
        controller.attached.connect(self._on_security_attached)
        controller.detached.connect(self._on_security_detached)
        controller.process_lost.connect(self._on_security_process_lost)

    @property
    def available(self) -> bool:
        return self.provider is not None and self.policy.mode is not AgentMode.OFF

    @property
    def busy(self) -> bool:
        return self._busy

    def configure_provider(self, provider: AIProvider | None, settings: AISettings) -> None:
        """Apply a CLI provider change and revoke any prior autonomous grant."""
        if self._busy:
            raise ProviderError(
                "Espera a que termine la respuesta actual antes de cambiar el proveedor."
            )
        self.provider = provider
        self.settings = settings.model_copy(deep=True)
        self.policy.write_limit = settings.autonomous_write_limit
        self.policy.writes_used = 0
        self.policy.mode = AgentMode.GUIDED if provider is not None else AgentMode.OFF
        self._autonomous_identity = None
        self.controller.autonomous_changed.emit(False, 0, self.policy.write_limit)
        self.mode_changed.emit(self.policy.mode.value)

    def submit(self, text: str) -> bool:
        """Start one worker job; return False when unavailable or already busy."""
        normalized = text.strip()
        if not normalized or not self.available or self._busy or self.provider is None:
            return False
        self.conversation.add_user(normalized)
        job = AgentTurnJob(
            self.provider,
            self.registry,
            self.conversation,
            self.flow,
            self.policy,
            self.settings.confirmation_timeout_s + 60.0,
        )
        self._set_busy(True)
        try:
            self.controller.start_agent_job(
                job,
                self.handle_tool_invocation,
                tool_timeout_s=self.settings.confirmation_timeout_s + 60.0,
            )
        except Exception:
            self._set_busy(False)
            raise
        return True

    def set_guided_mode(self) -> None:
        """Leave autonomous mode without disabling the configured provider."""
        if self.provider is None:
            self.policy.mode = AgentMode.OFF
        else:
            self.policy.mode = AgentMode.GUIDED
        self._autonomous_identity = None
        self.controller.autonomous_changed.emit(
            False, self.policy.writes_used, self.policy.write_limit
        )
        self.mode_changed.emit(self.policy.mode.value)

    def activate_autonomous_mode(self) -> bool:
        """Bind autonomous permission to the current anti-PID-reuse identity."""
        identity = self.controller.attached_identity()
        if self.provider is None or identity is None:
            return False
        self.policy.mode = AgentMode.AUTONOMOUS
        self.policy.bound_identity = identity
        self.policy.writes_used = 0
        self._autonomous_identity = identity
        self.controller.autonomous_changed.emit(True, 0, self.policy.write_limit)
        self.mode_changed.emit(AgentMode.AUTONOMOUS.value)
        return True

    def note_write_access(self, enabled: bool) -> None:
        self.flow.note_write_access(enabled)

    @Slot(object)
    def handle_tool_invocation(self, raw_invocation: object) -> None:
        """Evaluate and execute one request in the GUI thread, or await its card."""
        if not isinstance(raw_invocation, ToolInvocation):
            return
        tool = self._tools.get(raw_invocation.name)
        if tool is None:
            self._finish_invocation(
                raw_invocation,
                _error_json(
                    "unknown_tool",
                    "La herramienta solicitada no existe.",
                    "Usa una herramienta publicada por MemPilot.",
                ),
            )
            return
        effective_tool = self._effective_tool(tool, raw_invocation.arguments_json)
        previous_mode = self.policy.mode
        decision, reason = self.policy.evaluate(
            effective_tool,
            self.flow.snapshot().state,
            self.controller.attached_identity(),
        )
        if previous_mode is AgentMode.AUTONOMOUS and self.policy.mode is not previous_mode:
            self._autonomous_identity = None
            self.controller.autonomous_changed.emit(
                False, self.policy.writes_used, self.policy.write_limit
            )
            self.mode_changed.emit(self.policy.mode.value)
        self.activity.emit(_activity_start(raw_invocation.name, raw_invocation.arguments_json))
        if decision is Decision.DENY:
            self._finish_invocation(
                raw_invocation,
                _error_json("policy_denied", reason, "Sigue el paso indicado por la política."),
            )
            return
        if decision is Decision.CONFIRM:
            self._request_confirmation(raw_invocation)
            return
        self._execute_invocation(raw_invocation)

    def _request_confirmation(self, invocation: ToolInvocation) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)
        key = id(invocation)
        timer.timeout.connect(lambda: self._confirmation_timeout(key))
        self._pending[key] = _PendingConfirmation(invocation, timer)
        request = ConfirmationRequest(
            detail=self._confirmation_detail(invocation),
            confirm=lambda: self._resolve_confirmation(key, True),
            reject=lambda: self._resolve_confirmation(key, False),
        )
        self.controller.confirmation_required.emit(request)
        self.confirmation_requested.emit(request)
        timer.start(round(self.settings.confirmation_timeout_s * 1000))

    def _resolve_confirmation(self, key: int, confirmed: bool) -> None:
        pending = self._pending.pop(key, None)
        if pending is None:
            return
        pending.timer.stop()
        pending.timer.deleteLater()
        if confirmed:
            self._execute_invocation(pending.invocation)
        else:
            self._finish_invocation(
                pending.invocation,
                _error_json(
                    "confirmation_rejected",
                    "El usuario rechazó la confirmación.",
                    "No repitas la escritura sin una nueva indicación del usuario.",
                ),
            )

    def _confirmation_timeout(self, key: int) -> None:
        pending = self._pending.pop(key, None)
        if pending is None:
            return
        pending.timer.deleteLater()
        self._finish_invocation(
            pending.invocation,
            _error_json(
                "confirmation_timeout",
                "Confirmación expirada.",
                "Pregunta al usuario si desea volver a intentarlo.",
            ),
        )

    def _execute_invocation(self, invocation: ToolInvocation) -> None:
        result = self.registry.execute(invocation.name, invocation.arguments_json)
        if invocation.name == "attach_process" and _result_ok(result):
            arguments = _parse_arguments(invocation.arguments_json)
            self.flow.note_write_access(bool(arguments.get("write_access", False)))
        self._finish_invocation(invocation, result)

    def _finish_invocation(self, invocation: ToolInvocation, result_json: str) -> None:
        invocation.result_json = result_json
        invocation.done.set()
        self.activity.emit(_activity_result(invocation.name, result_json))
        if self.policy.mode is AgentMode.AUTONOMOUS:
            self.controller.autonomous_changed.emit(
                True, self.policy.writes_used, self.policy.write_limit
            )

    def _effective_tool(self, tool: ToolDef, arguments_json: str) -> ToolDef:
        if tool.name != "attach_process":
            return tool
        arguments = _parse_arguments(arguments_json)
        if arguments.get("write_access") is False:
            return replace(tool, mutating=False)
        return tool

    def _confirmation_detail(self, invocation: ToolInvocation) -> str:
        args = _parse_arguments(invocation.arguments_json)
        if invocation.name in {"write_watch", "freeze_watch"}:
            watch_id = str(args.get("watch_id", ""))
            watch = next(
                (item for item in self.controller.list_watches() if item.id == watch_id),
                None,
            )
            label = watch.label if watch is not None else watch_id
            current = watch.current_value if watch is not None else "desconocido"
            value = str(args.get("value", ""))
            return f"{invocation.name}: {label}\nValor actual: {current}\nValor nuevo: {value}"
        if invocation.name == "attach_process":
            return (
                f"Adjuntar al PID {args.get('pid')} con permiso de escritura: "
                f"{'sí' if args.get('write_access') else 'no'}"
            )
        if invocation.name == "load_workspace":
            return f"Cargar workspace: {args.get('name', '')}"
        return f"{invocation.name}: {invocation.arguments_json}"

    @Slot(object)
    def _on_agent_event(self, event: object) -> None:
        if isinstance(event, AgentRunResult):
            for text in event.texts:
                self.response_ready.emit(text)
        elif isinstance(event, MemPilotError):
            self.response_ready.emit(event.user_message())
        elif isinstance(event, BaseException):
            self.response_ready.emit(
                "El agente no pudo completar la solicitud. Revisa el estado e inténtalo de nuevo."
            )
        elif isinstance(event, str):
            self.response_ready.emit(event)
        self._set_busy(False)

    @Slot(object)
    def _on_security_attached(self, raw_identity: object) -> None:
        if (
            self.policy.mode is AgentMode.AUTONOMOUS
            and isinstance(raw_identity, ProcessIdentity)
            and self._autonomous_identity is not None
            and not raw_identity.matches(self._autonomous_identity)
        ):
            self.set_guided_mode()

    @Slot(str)
    def _on_security_detached(self, _reason: str) -> None:
        self._process_authorization_ended()

    @Slot(int)
    def _on_security_process_lost(self, _pid: int) -> None:
        self._process_authorization_ended()

    def _process_authorization_ended(self) -> None:
        for key in tuple(self._pending):
            self._resolve_confirmation(key, False)
        self.policy.bound_identity = None
        if self.policy.mode is AgentMode.AUTONOMOUS:
            self.set_guided_mode()
        self._autonomous_identity = None

    def _set_busy(self, busy: bool) -> None:
        if self._busy == busy:
            return
        self._busy = busy
        self.busy_changed.emit(busy)


def _parse_arguments(arguments_json: str) -> dict[str, Any]:
    try:
        value = json.loads(arguments_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _error_json(code: str, error: str, hint: str) -> str:
    return json.dumps(
        {"ok": False, "error_code": code, "error": error, "hint": hint},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _result_ok(result_json: str) -> bool:
    return _parse_arguments(result_json).get("ok") is True


def _activity_start(name: str, arguments_json: str) -> str:
    arguments = _parse_arguments(arguments_json)
    compact = ", ".join(f"{key}={value}" for key, value in arguments.items())
    return f"{name}({compact})"


def _activity_result(name: str, result_json: str) -> str:
    result = _parse_arguments(result_json)
    if result.get("ok") is True:
        for key in ("candidates", "total", "message", "value"):
            if key in result:
                return f"{name} → {result[key]}"
        return f"{name} → completado"
    return f"{name} → {result.get('error', 'error')}"
