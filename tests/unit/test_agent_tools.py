"""Security-boundary tests for ToolRegistry handlers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from mempilot.agent.policies import AgentPolicy
from mempilot.agent.tools import ToolRegistry
from mempilot.controller import Actor
from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.data_types import DataType
from mempilot.core.process_service import ProcessEntry
from mempilot.services.trainer_service import TrainerTrick, TrainerTrickState, TrickMode


class _ControllerStub:
    def __init__(self) -> None:
        self.saved_path: Path | None = None
        self.loaded_path: Path | None = None
        self.results_limit: int | None = None
        self.write_call: tuple[str, str, Actor] | None = None
        self.identity = ProcessIdentity(77, "memory_lab.exe", 10.0, None, Architecture.X64)
        self.trainer_save_call: tuple[object, ...] | None = None
        self.trainer_trick: TrainerTrick | None = None

    def list_processes(self, query: str, include_system: bool) -> list[ProcessEntry]:
        assert include_system is False
        return [
            ProcessEntry(
                pid=index + 10,
                name=f"{query or 'proceso'}-{index}-" + "x" * 300,
                path="C:/" + "p" * 300,
                architecture=Architecture.X64,
                username="usuario",
                is_system=False,
                can_attach=True,
                note="disponible",
            )
            for index in range(300)
        ]

    def attached_identity(self) -> ProcessIdentity:
        return self.identity

    def save_workspace(self, path: Path, actor: Actor) -> None:
        assert actor is Actor.AGENT
        self.saved_path = path

    def load_workspace(self, path: Path, actor: Actor) -> None:
        assert actor is Actor.AGENT
        self.loaded_path = path

    def set_watch_value(self, watch_id: str, value: str, actor: Actor) -> None:
        self.write_call = (watch_id, value, actor)

    def results_page(self, offset: int, limit: int, order: Any, filt: Any) -> Any:
        self.results_limit = limit
        return SimpleNamespace(rows=[], offset=offset, limit=limit, total=0, total_unfiltered=0)

    def list_trainer_tricks(self, actor: Actor) -> list[TrainerTrickState]:
        assert actor is Actor.AGENT
        return (
            [TrainerTrickState(self.trainer_trick, True)] if self.trainer_trick is not None else []
        )

    def save_trainer_trick(
        self,
        watch_id: str,
        name: str,
        enabled_value: str,
        disabled_value: str | None,
        mode: TrickMode,
        interval_ms: int,
        notes: str,
        actor: Actor,
    ) -> TrainerTrick:
        self.trainer_save_call = (
            watch_id,
            name,
            enabled_value,
            disabled_value,
            mode,
            interval_ms,
            notes,
            actor,
        )
        self.trainer_trick = TrainerTrick(
            id="trick-1",
            name=name,
            data_type=DataType.INT32,
            address_mode="absolute",
            address=0x1020,
            enabled_value=enabled_value,
            disabled_value=disabled_value,
            mode=mode,
            interval_ms=interval_ms,
        )
        return self.trainer_trick


def _registry(controller: _ControllerStub | None = None) -> ToolRegistry:
    return ToolRegistry(controller or _ControllerStub(), AgentPolicy())  # type: ignore[arg-type]


def test_registry_publishes_exact_step_31_tool_set() -> None:
    assert {tool.name for tool in _registry().tools} == {
        "list_processes",
        "attach_process",
        "detach_process",
        "get_attached_process",
        "start_scan",
        "refine_scan",
        "cancel_scan",
        "get_scan_status",
        "list_scan_results",
        "read_address",
        "add_watch",
        "list_watches",
        "write_watch",
        "list_trainer_tricks",
        "save_trainer_trick",
        "freeze_watch",
        "unfreeze_watch",
        "remove_watch",
        "save_workspace",
        "load_workspace",
    }


def test_execute_rejects_unknown_arguments_without_calling_handler() -> None:
    result = json.loads(_registry().execute("list_processes", '{"query":null,"extra":true}'))
    assert result["ok"] is False
    assert result["error_code"] == "invalid_arguments"


def test_execute_always_returns_json_and_hides_unexpected_exception() -> None:
    class _BrokenController(_ControllerStub):
        def list_processes(self, query: str, include_system: bool) -> list[ProcessEntry]:
            raise RuntimeError("technical secret")

    raw = _registry(_BrokenController()).execute("list_processes", '{"query":null}')
    result = json.loads(raw)
    assert result["ok"] is False
    assert result["error_code"] == "internal_error"
    assert "technical secret" not in raw


def test_process_output_is_limited_to_200_rows_and_8_kib() -> None:
    raw = _registry().execute("list_processes", '{"query":"lab"}')
    result = json.loads(raw)
    assert result["ok"] is True
    assert len(result["processes"]) <= 200
    assert result["truncated"] is True
    assert len(raw.encode("utf-8")) <= 8 * 1024


def test_result_handler_clamps_requested_page_to_200() -> None:
    controller = _ControllerStub()
    payload = {
        "offset": None,
        "limit": 50_000,
        "sort": None,
        "descending": None,
        "filter_text": None,
    }
    result = json.loads(_registry(controller).execute("list_scan_results", json.dumps(payload)))
    assert result["ok"] is True
    assert controller.results_limit == 200


def test_workspace_names_are_slugged_and_confined(monkeypatch: Any, tmp_path: Path) -> None:
    import mempilot.agent.tools as tools_module

    controller = _ControllerStub()
    monkeypatch.setattr(tools_module, "WORKSPACE_DIR", tmp_path)
    result = json.loads(
        _registry(controller).execute("save_workspace", '{"name":"Partida Ágil.json"}')
    )
    assert result["ok"] is True
    assert controller.saved_path == tmp_path.resolve() / "partida-agil.json"
    assert controller.saved_path is not None
    assert controller.saved_path.resolve().is_relative_to(tmp_path.resolve())


def test_workspace_traversal_is_rejected_before_controller_call(
    monkeypatch: Any, tmp_path: Path
) -> None:
    import mempilot.agent.tools as tools_module

    controller = _ControllerStub()
    monkeypatch.setattr(tools_module, "WORKSPACE_DIR", tmp_path)
    result = json.loads(_registry(controller).execute("load_workspace", '{"name":"../../escape"}'))
    assert result["ok"] is False
    assert result["error_code"] == "invalid_operation"
    assert controller.loaded_path is None


def test_mutating_handler_uses_agent_actor() -> None:
    controller = _ControllerStub()
    result = json.loads(
        _registry(controller).execute("write_watch", '{"watch_id":"watch-1","value":"250"}')
    )
    assert result["ok"] is True
    assert controller.write_call == ("watch-1", "250", Actor.AGENT)


def test_save_trainer_tool_uses_agent_actor_and_typed_mode() -> None:
    controller = _ControllerStub()
    result = json.loads(
        _registry(controller).execute(
            "save_trainer_trick",
            json.dumps(
                {
                    "watch_id": "watch-1",
                    "name": "Vida infinita",
                    "enabled_value": "100",
                    "disabled_value": None,
                    "mode": "freeze",
                    "interval_ms": 75,
                    "notes": "Probado por el usuario.",
                }
            ),
        )
    )

    assert result["ok"] is True
    assert result["trick"]["name"] == "Vida infinita"
    assert controller.trainer_save_call == (
        "watch-1",
        "Vida infinita",
        "100",
        None,
        TrickMode.FREEZE,
        75,
        "Probado por el usuario.",
        Actor.AGENT,
    )


def test_every_tool_returns_json_for_malformed_or_empty_input() -> None:
    registry = _registry()
    for tool in registry.tools:
        raw = registry.execute(tool.name, "{}")
        assert isinstance(json.loads(raw), dict)
        assert len(raw.encode("utf-8")) <= 8 * 1024
