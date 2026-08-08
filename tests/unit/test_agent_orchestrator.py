"""Focused sequential workflow tests using only ScriptedProvider."""

from __future__ import annotations

import json
import threading
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict
from PySide6.QtCore import QObject, Signal

from mempilot.agent.orchestrator import (
    AgentOrchestrator,
    AgentTurnJob,
    ConfirmationRequest,
    FlowMachine,
)
from mempilot.agent.policies import AgentMode, AgentPolicy, FlowState
from mempilot.agent.providers import ProviderTurn, ScriptedProvider, ToolCall
from mempilot.agent.tools import ToolDef
from mempilot.config.settings import AISettings
from mempilot.controller import ScanStatus
from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.data_types import DataType
from mempilot.core.scan_session import ScanSession, SessionState
from mempilot.core.scanner import CandidateSet, ScanMode, ScanOptions, ScanRequest
from mempilot.core.watcher import WatchEntry, WatchSpec
from mempilot.ui.workers import ToolInvocation


class _NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Controller(QObject):
    attached = Signal(object)
    detached = Signal(str)
    process_lost = Signal(int)
    scan_started = Signal(object)
    scan_finished = Signal(object)
    watches_changed = Signal()
    agent_event = Signal(object)
    confirmation_required = Signal(object)
    autonomous_changed = Signal(bool, int, int)

    def __init__(self) -> None:
        super().__init__()
        self.identity = ProcessIdentity(4242, "target.exe", 10.0, "C:/target.exe", Architecture.X64)
        self.status = ScanStatus(None, SessionState.NEW, None, None, 0, None, 0, None)
        self.watches: list[WatchEntry] = []

    def attached_identity(self) -> ProcessIdentity | None:
        return self.identity

    def scan_status(self) -> ScanStatus:
        return self.status

    def list_watches(self) -> list[WatchEntry]:
        return list(self.watches)


class _Registry:
    def __init__(self, controller: _Controller) -> None:
        self.controller = controller
        self.executed: list[str] = []
        definitions = (
            ("start_scan", False, frozenset({FlowState.ATTACHED})),
            (
                "refine_scan",
                False,
                frozenset({FlowState.CANDIDATES, FlowState.AWAITING_CHANGE}),
            ),
            ("add_watch", False, frozenset({FlowState.NARROWED})),
            ("freeze_watch", True, frozenset({FlowState.WATCHING})),
            ("attach_process", True, frozenset({FlowState.NO_PROCESS})),
        )
        self.tools = tuple(
            ToolDef(name, name, _NoArgs, lambda _args: _NoArgs(), mutating, False, states)
            for name, mutating, states in definitions
        )

    def specs(self) -> list[dict[str, Any]]:
        return [{"type": "function", "name": item.name} for item in self.tools]

    def execute(self, name: str, arguments_json: str) -> str:
        self.executed.append(name)
        args = json.loads(arguments_json)
        if name == "start_scan":
            request = ScanRequest(DataType.INT32, ScanMode.EXACT, "100", None, ScanOptions())
            self.controller.status = ScanStatus(
                "scan", SessionState.SCANNING, DataType.INT32, ScanMode.EXACT, 0, None, 0, None
            )
            self.controller.scan_started.emit(request)
            self._finish_scan(12, ScanMode.EXACT)
            return '{"ok":true,"session_id":"scan","state":"scanning"}'
        if name == "refine_scan":
            request = ScanRequest(DataType.INT32, ScanMode.EXACT, "73", None, ScanOptions())
            self.controller.status = ScanStatus(
                "scan", SessionState.SCANNING, DataType.INT32, ScanMode.EXACT, 12, None, 0, None
            )
            self.controller.scan_started.emit(request)
            self._finish_scan(3, ScanMode.EXACT)
            return '{"ok":true,"session_id":"scan","state":"scanning"}'
        if name == "add_watch":
            watch = WatchEntry.from_spec(
                WatchSpec("Vida", DataType.INT32, address=int(args["address"])),
                watch_id="life",
            )
            watch.current_value = "73"
            self.controller.watches.append(watch)
            self.controller.watches_changed.emit()
            return '{"ok":true,"watch":{"id":"life"}}'
        if name == "freeze_watch":
            self.controller.watches[0].frozen = True
            self.controller.watches[0].desired_value = str(args["value"])
            self.controller.watches_changed.emit()
            return '{"ok":true,"message":"Vigilancia congelada."}'
        return '{"ok":true}'

    def _finish_scan(self, candidates: int, mode: ScanMode) -> None:
        session = ScanSession(self.controller.identity, DataType.INT32, ScanOptions())
        session.result = CandidateSet(
            np.arange(0x1000, 0x1000 + candidates, dtype=np.uint64),
            np.full(candidates, 73, dtype=np.int32),
            DataType.INT32,
        )
        session.state = SessionState.READY
        session.last_mode = mode
        self.controller.status = ScanStatus(
            "scan",
            SessionState.READY,
            DataType.INT32,
            mode,
            candidates,
            None,
            0 if candidates > 5 else 1,
            None,
        )
        self.controller.scan_finished.emit(session)


def _call(call_id: str, name: str, arguments: dict[str, object]) -> ProviderTurn:
    return ProviderTurn(
        "",
        [ToolCall(call_id, name, json.dumps(arguments, separators=(",", ":")))],
        [],
    )


def test_scripted_cycle_scan_refine_watch_freeze_and_signal_states() -> None:
    controller = _Controller()
    registry = _Registry(controller)
    policy = AgentPolicy(
        AgentMode.AUTONOMOUS,
        write_limit=2,
        bound_identity=controller.identity,
    )
    provider = ScriptedProvider(
        [
            _call("1", "start_scan", {}),
            _call("2", "refine_scan", {}),
            _call("3", "add_watch", {"address": 4096}),
            _call("4", "freeze_watch", {"watch_id": "life", "value": "100"}),
            ProviderTurn("Vida localizada y congelada.", [], []),
        ]
    )
    orchestrator = AgentOrchestrator(
        controller,  # type: ignore[arg-type]
        registry,  # type: ignore[arg-type]
        policy,
        provider,
        AISettings(confirmation_timeout_s=1),
    )
    states: list[FlowState] = []
    controller.scan_started.connect(lambda _request: states.append(orchestrator.flow.state))
    controller.scan_finished.connect(lambda _session: states.append(orchestrator.flow.state))
    controller.watches_changed.connect(lambda: states.append(orchestrator.flow.state))
    orchestrator.conversation.add_user("Encuentra y congela la vida")
    job = AgentTurnJob(
        provider,
        registry,  # type: ignore[arg-type]
        orchestrator.conversation,
        orchestrator.flow,
        policy,
        1,
    )

    def execute(name: str, arguments: str, _timeout: float | None) -> str:
        invocation = ToolInvocation(name, arguments)
        orchestrator.handle_tool_invocation(invocation)
        assert invocation.done.is_set()
        return invocation.result_json

    result = job.run(threading.Event(), execute)

    assert registry.executed == ["start_scan", "refine_scan", "add_watch", "freeze_watch"]
    assert FlowState.SCANNING in states
    assert FlowState.CANDIDATES in states
    assert FlowState.NARROWED in states
    assert states[-1] is FlowState.WATCHING
    assert policy.writes_used == 1
    assert result.texts[-1] == "Vida localizada y congelada."


def test_rejected_confirmation_returns_structured_error_and_loop_continues() -> None:
    controller = _Controller()
    registry = _Registry(controller)
    watch = WatchEntry.from_spec(WatchSpec("Vida", DataType.INT32, address=0x1000), watch_id="life")
    watch.current_value = "73"
    controller.watches.append(watch)
    policy = AgentPolicy(AgentMode.GUIDED, bound_identity=controller.identity)
    provider = ScriptedProvider(
        [
            _call("freeze", "freeze_watch", {"watch_id": "life", "value": "100"}),
            ProviderTurn("Entendido; no modifiqué el valor.", [], []),
        ]
    )
    orchestrator = AgentOrchestrator(
        controller,  # type: ignore[arg-type]
        registry,  # type: ignore[arg-type]
        policy,
        provider,
        AISettings(confirmation_timeout_s=1),
    )
    controller.watches_changed.emit()
    confirmations: list[ConfirmationRequest] = []
    orchestrator.confirmation_requested.connect(confirmations.append)
    orchestrator.conversation.add_user("Congélala")
    job = AgentTurnJob(
        provider,
        registry,  # type: ignore[arg-type]
        orchestrator.conversation,
        orchestrator.flow,
        policy,
        1,
    )

    def reject(name: str, arguments: str, _timeout: float | None) -> str:
        invocation = ToolInvocation(name, arguments)
        orchestrator.handle_tool_invocation(invocation)
        confirmations[-1].reject()
        assert invocation.done.is_set()
        return invocation.result_json

    result = job.run(threading.Event(), reject)

    replay = provider.requests[1][1]
    output = next(item for item in replay if item.get("type") == "function_call_output")
    assert json.loads(output["output"])["error_code"] == "confirmation_rejected"
    assert registry.executed == []
    assert result.texts == ("Entendido; no modifiqué el valor.",)


def test_autonomous_mode_denies_process_change_and_enforces_write_limit() -> None:
    controller = _Controller()
    registry = _Registry(controller)
    controller.watches.append(
        WatchEntry.from_spec(WatchSpec("Vida", DataType.INT32, address=0x1000), watch_id="life")
    )
    policy = AgentPolicy(
        AgentMode.AUTONOMOUS,
        write_limit=1,
        bound_identity=controller.identity,
    )
    orchestrator = AgentOrchestrator(
        controller,  # type: ignore[arg-type]
        registry,  # type: ignore[arg-type]
        policy,
        ScriptedProvider([]),
        AISettings(),
    )
    controller.watches_changed.emit()
    first = ToolInvocation("freeze_watch", '{"watch_id":"life","value":"100"}')
    second = ToolInvocation("freeze_watch", '{"watch_id":"life","value":"90"}')
    attach = ToolInvocation("attach_process", '{"pid":7,"write_access":true}')

    orchestrator.handle_tool_invocation(first)
    orchestrator.handle_tool_invocation(second)
    orchestrator.handle_tool_invocation(attach)

    assert json.loads(first.result_json)["ok"] is True
    assert json.loads(second.result_json)["error_code"] == "policy_denied"
    assert "límite" in json.loads(second.result_json)["error"].casefold()
    assert json.loads(attach.result_json)["error_code"] == "policy_denied"
    assert registry.executed == ["freeze_watch"]


def test_flow_machine_detach_and_process_lost_reset_to_no_process() -> None:
    controller = _Controller()
    machine = FlowMachine(controller)  # type: ignore[arg-type]
    assert machine.state is FlowState.ATTACHED
    controller.detached.emit("usuario")
    assert machine.state is FlowState.NO_PROCESS
    controller.identity = ProcessIdentity(7, "new.exe", 20.0, None, Architecture.X64)
    controller.attached.emit(controller.identity)
    assert machine.state is FlowState.ATTACHED
    controller.process_lost.emit(7)
    assert machine.state is FlowState.NO_PROCESS
