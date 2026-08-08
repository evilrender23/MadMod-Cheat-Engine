"""Focused tests for portable, versioned workspace persistence."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mempilot.core.backend import Architecture
from mempilot.core.data_types import DataType
from mempilot.core.exceptions import WorkspaceError
from mempilot.core.pointer_chain import PointerChain
from mempilot.services.workspace_service import (
    WatchEntryModel,
    WorkspaceModel,
    load_workspace,
    save_workspace,
)


def _workspace() -> WorkspaceModel:
    now = datetime.now(UTC)
    return WorkspaceModel(
        created_at=now,
        updated_at=now,
        process_name="memory_lab.exe",
        process_path="C:/Lab/memory_lab.exe",
        architecture=Architecture.X64,
        watches=[
            WatchEntryModel(
                id="watch-health-unique",
                label="Vida",
                address_mode="module_offset",
                module="memory_lab.exe",
                offset=0x1234,
                data_type=DataType.INT32,
                desired_value="100",
                frozen=True,
                notes="Vigilancia principal",
            )
        ],
        pointer_chains=[
            PointerChain(
                id="chain-health-unique",
                label="Puntero de vida",
                module="memory_lab.exe",
                base_offset=0x2000,
                offsets=[0x10, 0x28],
                data_type=DataType.INT32,
            )
        ],
        tags=["demostración"],
    )


def test_workspace_round_trip_preserves_watches_and_chains(tmp_path: Path) -> None:
    path = tmp_path / "lab.json"
    expected = _workspace()

    save_workspace(path, expected)
    loaded = load_workspace(path)

    assert loaded == expected
    assert loaded.watches[0].id == "watch-health-unique"
    assert loaded.pointer_chains[0].offsets == [0x10, 0x28]
    assert "demostración" in path.read_text(encoding="utf-8")
    assert not (tmp_path / "lab.json.tmp").exists()


def test_workspace_rejects_other_schema_versions(tmp_path: Path) -> None:
    path = tmp_path / "future.json"
    document = json.loads(_workspace().model_dump_json())
    document["schema_version"] = 2
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(WorkspaceError, match="versión incompatible"):
        load_workspace(path)


def test_workspace_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "extra.json"
    document = json.loads(_workspace().model_dump_json())
    document["handle"] = 12345
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(WorkspaceError):
        load_workspace(path)


def test_workspace_contains_no_runtime_or_secret_data(tmp_path: Path) -> None:
    path = tmp_path / "safe.json"
    workspace = _workspace()
    workspace.notes = "accidental sk-workspace-secret-123456789"

    save_workspace(path, workspace)

    raw = path.read_text(encoding="utf-8")
    document = json.loads(raw)
    assert document["notes"] == "accidental ***"
    assert '"pid"' not in raw
    assert '"handle"' not in raw
    assert '"resolved_address"' not in raw
    assert "sk-" not in raw
