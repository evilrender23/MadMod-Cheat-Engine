"""Versioned workspace models and atomic persistence."""

from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mempilot.core.backend import Architecture
from mempilot.core.data_types import DataType
from mempilot.core.exceptions import WorkspaceError
from mempilot.core.pointer_chain import PointerChain
from mempilot.i18n import t
from mempilot.logging_setup import redact_secrets


class WatchEntryModel(BaseModel):
    """Serializable watch definition without runtime state."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    address_mode: Literal["absolute", "module_offset", "pointer_chain"]
    address: int | None = None
    module: str | None = None
    offset: int | None = None
    chain_id: str | None = None
    data_type: DataType
    desired_value: str | None = None
    frozen: bool = False
    interval_ms: int = Field(default=100, ge=50, le=5000)
    notes: str = ""


class WorkspaceModel(BaseModel):
    """Versioned, portable workspace document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    created_at: datetime
    updated_at: datetime
    process_name: str
    process_path: str | None
    architecture: Architecture
    watches: list[WatchEntryModel] = Field(default_factory=list)
    pointer_chains: list[PointerChain] = Field(default_factory=list)
    watch_refresh_ms: int = Field(default=100, ge=50, le=5000)
    results_refresh_ms: int = Field(default=500, ge=50, le=5000)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    history: list[dict[str, str]] = Field(default_factory=list)


def save_workspace(path: Path, ws: WorkspaceModel) -> None:
    """Atomically save a UTF-8 workspace document beside a temporary file."""
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = redact_secrets(ws.model_dump_json(indent=2, ensure_ascii=False)) + "\n"
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise WorkspaceError(t("workspace.save_failed", path=path)) from exc
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)


def load_workspace(path: Path) -> WorkspaceModel:
    """Load and validate a schema-version-1 workspace."""
    try:
        raw = path.read_text(encoding="utf-8")
        return WorkspaceModel.model_validate_json(raw)
    except (OSError, ValidationError, ValueError) as exc:
        raise WorkspaceError(t("workspace.version_invalid")) from exc
