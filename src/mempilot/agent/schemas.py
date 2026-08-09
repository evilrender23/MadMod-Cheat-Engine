"""Strict Pydantic schemas exposed to the AI tool boundary."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mempilot.core.data_types import DataType
from mempilot.core.scanner import ScanMode
from mempilot.i18n import t
from mempilot.services.trainer_service import TrickMode

_PROHIBITED_SCHEMA_KEYWORDS = frozenset(
    {
        "allOf",
        "not",
        "if",
        "then",
        "else",
        "dependentRequired",
        "dependentSchemas",
    }
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return the strict JSON Schema subset accepted by Responses tools."""
    schema = model.model_json_schema()

    def normalize(node: Any) -> None:
        if isinstance(node, dict):
            prohibited = _PROHIBITED_SCHEMA_KEYWORDS.intersection(node)
            if prohibited:
                names = ", ".join(sorted(prohibited))
                raise ValueError(t("schema.unsupported", keywords=names))
            node.pop("default", None)
            node.pop("title", None)
            properties = node.get("properties")
            if node.get("type") == "object" or isinstance(properties, dict):
                object_properties = properties if isinstance(properties, dict) else {}
                node["properties"] = object_properties
                node["additionalProperties"] = False
                node["required"] = list(object_properties)
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(schema)
    return schema


class ListProcessesArgs(_StrictModel):
    query: str | None


class AttachProcessArgs(_StrictModel):
    pid: int = Field(ge=1, le=4_294_967_295)
    write_access: bool


class DetachProcessArgs(_StrictModel):
    pass


class GetAttachedProcessArgs(_StrictModel):
    pass


class StartScanArgs(_StrictModel):
    data_type: DataType
    scan_mode: ScanMode
    value: str | None
    value2: str | None
    alignment: int | None
    writable_only: bool | None
    float_tolerance: float | None
    case_sensitive: bool | None
    timeout_ms: int | None


class RefineScanArgs(_StrictModel):
    scan_mode: ScanMode
    value: str | None
    value2: str | None
    timeout_ms: int | None


class CancelScanArgs(_StrictModel):
    pass


class GetScanStatusArgs(_StrictModel):
    pass


class ListScanResultsArgs(_StrictModel):
    offset: int | None
    limit: int | None
    sort: Literal["address", "value", "change_rate"] | None
    descending: bool | None
    filter_text: str | None


class ReadAddressArgs(_StrictModel):
    address: int = Field(ge=0)
    data_type: DataType


class AddWatchArgs(_StrictModel):
    address: int = Field(ge=0)
    data_type: DataType
    label: str


class ListWatchesArgs(_StrictModel):
    pass


class WriteWatchArgs(_StrictModel):
    watch_id: str
    value: str


class FreezeWatchArgs(_StrictModel):
    watch_id: str
    value: str
    interval_ms: int | None


class UnfreezeWatchArgs(_StrictModel):
    watch_id: str


class RemoveWatchArgs(_StrictModel):
    watch_id: str


class ListTrainerTricksArgs(_StrictModel):
    pass


class SaveTrainerTrickArgs(_StrictModel):
    watch_id: str
    name: str
    enabled_value: str
    disabled_value: str | None
    mode: TrickMode
    interval_ms: int | None
    notes: str | None


class SaveWorkspaceArgs(_StrictModel):
    name: str


class LoadWorkspaceArgs(_StrictModel):
    name: str


class ErrorResult(_StrictModel):
    ok: bool
    error_code: str
    error: str
    hint: str


class OperationResult(_StrictModel):
    ok: bool
    message: str


class ProcessResult(_StrictModel):
    pid: int
    name: str
    path: str | None
    architecture: str
    username: str | None
    is_system: bool
    can_attach: bool
    note: str


class ProcessListResult(_StrictModel):
    ok: bool
    processes: list[ProcessResult]
    count: int
    truncated: bool


class AttachedProcessResult(_StrictModel):
    ok: bool
    attached: bool
    pid: int | None
    name: str | None
    path: str | None
    architecture: str | None
    write_access: bool | None


class ScanStartedResult(_StrictModel):
    ok: bool
    session_id: str
    state: str
    timeout_ms: int | None


class ScanStatusResult(_StrictModel):
    ok: bool
    session_id: str | None
    state: str
    data_type: str | None
    last_mode: str | None
    candidates: int
    refinements: int
    error: str | None


class ScanResultRow(_StrictModel):
    address: int
    address_hex: str
    current: str
    previous: str
    data_type: str
    region: str
    protection: str
    change_rate: float
    readable: bool
    writable: bool


class ScanResultsResult(_StrictModel):
    ok: bool
    rows: list[ScanResultRow]
    offset: int
    limit: int
    total: int
    total_unfiltered: int
    truncated: bool


class AddressReadResult(_StrictModel):
    ok: bool
    address: int
    address_hex: str
    data_type: str
    value: str


class WatchResult(_StrictModel):
    id: str
    label: str
    data_type: str
    address: int | None
    module: str | None
    offset: int | None
    interval_ms: int
    notes: str
    frozen: bool
    desired_value: str | None
    current_value: str
    last_error: str | None


class WatchAddedResult(_StrictModel):
    ok: bool
    watch: WatchResult


class WatchListResult(_StrictModel):
    ok: bool
    watches: list[WatchResult]
    count: int
    truncated: bool


class TrainerTrickResult(_StrictModel):
    id: str
    name: str
    data_type: str
    mode: str
    enabled_value: str
    disabled_value: str | None
    interval_ms: int
    notes: str
    active: bool


class TrainerTrickSavedResult(_StrictModel):
    ok: bool
    process_name: str
    trick: TrainerTrickResult


class TrainerTrickListResult(_StrictModel):
    ok: bool
    process_name: str
    tricks: list[TrainerTrickResult]
    count: int


class WorkspaceResult(_StrictModel):
    ok: bool
    name: str
    message: str
