"""Typed, size-bounded tool boundary over :class:`AppController`."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from mempilot.agent.policies import AgentPolicy, FlowState
from mempilot.agent.schemas import (
    AddressReadResult,
    AddWatchArgs,
    AttachedProcessResult,
    AttachProcessArgs,
    CancelScanArgs,
    DetachProcessArgs,
    ErrorResult,
    FreezeWatchArgs,
    GetAttachedProcessArgs,
    GetScanStatusArgs,
    ListProcessesArgs,
    ListScanResultsArgs,
    ListWatchesArgs,
    LoadWorkspaceArgs,
    OperationResult,
    ProcessListResult,
    ProcessResult,
    ReadAddressArgs,
    RefineScanArgs,
    RemoveWatchArgs,
    SaveWorkspaceArgs,
    ScanResultRow,
    ScanResultsResult,
    ScanStartedResult,
    ScanStatusResult,
    StartScanArgs,
    UnfreezeWatchArgs,
    WatchAddedResult,
    WatchListResult,
    WatchResult,
    WorkspaceResult,
    WriteWatchArgs,
    strict_schema,
)
from mempilot.config.paths import WORKSPACE_DIR
from mempilot.controller import Actor, AppController
from mempilot.core.backend import ProcessIdentity
from mempilot.core.exceptions import MemPilotError
from mempilot.core.scan_session import FilterSpec, OrderSpec
from mempilot.core.scanner import ScanOptions, ScanRequest
from mempilot.core.watcher import WatchEntry, WatchSpec

_MAX_ROWS = 200
_MAX_JSON_BYTES = 8 * 1024
_MAX_TEXT = 256
_DEFAULT_TIMEOUT_MS = 30_000


@dataclass(frozen=True, slots=True)
class ToolDef:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel]
    mutating: bool
    requires_attached: bool
    allowed_states: frozenset[FlowState] | None


class ToolRegistry:
    """Validate and execute agent tools without exposing controller internals."""

    def __init__(self, controller: AppController, policy: AgentPolicy) -> None:
        self.controller = controller
        self.policy = policy
        definitions = self._build_definitions()
        self.tools = tuple(definitions)
        self._by_name = {tool.name: tool for tool in definitions}

    def specs(self) -> list[dict[str, Any]]:
        """Return flat strict function definitions for the Responses API."""
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": strict_schema(tool.args_model),
                "strict": True,
            }
            for tool in self.tools
        ]

    def execute(self, name: str, arguments_json: str) -> str:
        """Execute one validated tool and always return bounded JSON."""
        try:
            tool = self._by_name.get(name)
            if tool is None:
                return self._serialize_error(
                    "unknown_tool",
                    "La herramienta solicitada no existe.",
                    "Usa una de las herramientas publicadas por MemPilot.",
                )
            try:
                arguments = tool.args_model.model_validate_json(arguments_json)
            except ValidationError:
                return self._serialize_error(
                    "invalid_arguments",
                    "Los argumentos no tienen el formato requerido.",
                    "Corrige los campos indicados por el esquema estricto y vuelve a intentarlo.",
                )
            result = tool.handler(arguments)
            return self._serialize(result)
        except MemPilotError as exc:
            return self._serialize_error(
                _error_code(exc),
                exc.user_message(),
                "Corrige la causa indicada y vuelve a intentar la operación.",
            )
        except ValueError as exc:
            return self._serialize_error(
                "invalid_operation",
                str(exc) or "La operación solicitada no es válida.",
                "Revisa los datos y el estado actual antes de volver a intentarlo.",
            )
        except Exception:
            return self._serialize_error(
                "internal_error",
                "MemPilot no pudo completar la herramienta de forma segura.",
                "Revisa el estado de la aplicación y vuelve a intentarlo.",
            )

    def _serialize(self, result: BaseModel) -> str:
        serialized = result.model_dump_json()
        if len(serialized.encode("utf-8")) <= _MAX_JSON_BYTES:
            return serialized
        return self._serialize_error(
            "response_too_large",
            "La respuesta supera el límite seguro de tamaño.",
            "Usa un filtro más específico o solicita una página más pequeña.",
        )

    @staticmethod
    def _serialize_error(error_code: str, error: str, hint: str) -> str:
        result = ErrorResult(
            ok=False,
            error_code=_clip(error_code, 64),
            error=_clip(error, 512),
            hint=_clip(hint, 256),
        )
        return result.model_dump_json()

    def _build_definitions(self) -> list[ToolDef]:
        attached_states = frozenset(
            {
                FlowState.ATTACHED,
                FlowState.CANDIDATES,
                FlowState.AWAITING_CHANGE,
                FlowState.NARROWED,
                FlowState.WATCHING,
            }
        )
        result_states = frozenset(
            {
                FlowState.CANDIDATES,
                FlowState.AWAITING_CHANGE,
                FlowState.NARROWED,
                FlowState.WATCHING,
            }
        )
        return [
            ToolDef(
                "list_processes",
                "Lista procesos locales autorizados; úsala antes de proponer cuál seleccionar.",
                ListProcessesArgs,
                self._list_processes,
                False,
                False,
                None,
            ),
            ToolDef(
                "attach_process",
                "Adjunta MemPilot a un PID; úsala solo tras la selección explícita del usuario.",
                AttachProcessArgs,
                self._attach_process,
                True,
                False,
                frozenset({FlowState.NO_PROCESS}),
            ),
            ToolDef(
                "detach_process",
                "Desacopla el proceso actual; úsala cuando el usuario quiera terminar la sesión.",
                DetachProcessArgs,
                self._detach_process,
                False,
                True,
                attached_states | frozenset({FlowState.SCANNING}),
            ),
            ToolDef(
                "get_attached_process",
                "Consulta el proceso vinculado; úsala para confirmar identidad y arquitectura.",
                GetAttachedProcessArgs,
                self._get_attached_process,
                False,
                False,
                None,
            ),
            ToolDef(
                "start_scan",
                "Inicia un primer escaneo tipado; úsala después de conocer el valor inicial.",
                StartScanArgs,
                self._start_scan,
                False,
                True,
                attached_states,
            ),
            ToolDef(
                "refine_scan",
                "Refina los candidatos actuales; úsala después de que el usuario "
                "provoque un cambio.",
                RefineScanArgs,
                self._refine_scan,
                False,
                True,
                result_states,
            ),
            ToolDef(
                "cancel_scan",
                "Cancela el escaneo en curso; úsala cuando el usuario lo solicite.",
                CancelScanArgs,
                self._cancel_scan,
                False,
                True,
                frozenset({FlowState.SCANNING}),
            ),
            ToolDef(
                "get_scan_status",
                "Consulta estado y candidatos; úsala antes de decidir el siguiente paso.",
                GetScanStatusArgs,
                self._get_scan_status,
                False,
                False,
                None,
            ),
            ToolDef(
                "list_scan_results",
                "Devuelve una página acotada de candidatos; úsala para inspeccionar "
                "pocos resultados.",
                ListScanResultsArgs,
                self._list_scan_results,
                False,
                True,
                result_states,
            ),
            ToolDef(
                "read_address",
                "Lee una dirección conocida con un tipo concreto; nunca inventes la dirección.",
                ReadAddressArgs,
                self._read_address,
                False,
                True,
                attached_states,
            ),
            ToolDef(
                "add_watch",
                "Añade una dirección candidata a vigilancia; úsala cuando queden pocos candidatos.",
                AddWatchArgs,
                self._add_watch,
                False,
                True,
                result_states,
            ),
            ToolDef(
                "list_watches",
                "Lista las vigilancias actuales; úsala antes de escribir, congelar o eliminar.",
                ListWatchesArgs,
                self._list_watches,
                False,
                True,
                attached_states,
            ),
            ToolDef(
                "write_watch",
                "Escribe un valor en una vigilancia existente; requiere autorización de escritura.",
                WriteWatchArgs,
                self._write_watch,
                True,
                True,
                attached_states,
            ),
            ToolDef(
                "freeze_watch",
                "Congela una vigilancia en un valor; requiere autorización "
                "y tiene escritura periódica.",
                FreezeWatchArgs,
                self._freeze_watch,
                True,
                True,
                attached_states,
            ),
            ToolDef(
                "unfreeze_watch",
                "Descongela una vigilancia; úsala para detener sus escrituras periódicas.",
                UnfreezeWatchArgs,
                self._unfreeze_watch,
                False,
                True,
                attached_states,
            ),
            ToolDef(
                "remove_watch",
                "Elimina una vigilancia; úsala solo para una entrada identificada por su id.",
                RemoveWatchArgs,
                self._remove_watch,
                False,
                True,
                attached_states,
            ),
            ToolDef(
                "save_workspace",
                "Guarda la sesión en la carpeta segura de workspaces usando solo un nombre.",
                SaveWorkspaceArgs,
                self._save_workspace,
                False,
                True,
                attached_states,
            ),
            ToolDef(
                "load_workspace",
                "Carga una sesión desde la carpeta segura de workspaces usando solo un nombre.",
                LoadWorkspaceArgs,
                self._load_workspace,
                True,
                True,
                attached_states,
            ),
        ]

    def _list_processes(self, base: BaseModel) -> BaseModel:
        args = cast(ListProcessesArgs, base)
        entries = self.controller.list_processes(args.query or "", include_system=False)
        items = [
            ProcessResult(
                pid=entry.pid,
                name=_clip(entry.name),
                path=_clip_optional(entry.path),
                architecture=entry.architecture.value,
                username=_clip_optional(entry.username),
                is_system=entry.is_system,
                can_attach=entry.can_attach,
                note=_clip(entry.note),
            )
            for entry in entries[:_MAX_ROWS]
        ]
        return _bounded_prefix(
            items,
            lambda values, clipped: ProcessListResult(
                ok=True,
                processes=values,
                count=len(entries),
                truncated=clipped or len(entries) > len(values),
            ),
        )

    def _attach_process(self, base: BaseModel) -> BaseModel:
        args = cast(AttachProcessArgs, base)
        identity = self.controller.attach(args.pid, args.write_access, Actor.AGENT)
        return _attached_result(identity, args.write_access)

    def _detach_process(self, base: BaseModel) -> BaseModel:
        cast(DetachProcessArgs, base)
        self.controller.detach(
            "Desacoplado por el agente con autorización del usuario.", Actor.AGENT
        )
        return OperationResult(ok=True, message="Proceso desacoplado.")

    def _get_attached_process(self, base: BaseModel) -> BaseModel:
        cast(GetAttachedProcessArgs, base)
        identity = self.controller.attached_identity()
        if identity is None:
            return AttachedProcessResult(
                ok=True,
                attached=False,
                pid=None,
                name=None,
                path=None,
                architecture=None,
                write_access=None,
            )
        return _attached_result(identity, None)

    def _start_scan(self, base: BaseModel) -> BaseModel:
        args = cast(StartScanArgs, base)
        timeout_ms = _timeout(args.timeout_ms)
        defaults = ScanOptions()
        options = ScanOptions(
            alignment=defaults.alignment if args.alignment is None else args.alignment,
            writable_only=defaults.writable_only
            if args.writable_only is None
            else args.writable_only,
            include_image=defaults.include_image,
            include_mapped=defaults.include_mapped,
            use_tolerance=defaults.use_tolerance,
            float_tolerance=defaults.float_tolerance
            if args.float_tolerance is None
            else args.float_tolerance,
            case_sensitive=defaults.case_sensitive
            if args.case_sensitive is None
            else args.case_sensitive,
            chunk_size=defaults.chunk_size,
            max_candidates=defaults.max_candidates,
            unknown_budget_mb=defaults.unknown_budget_mb,
            address_min=defaults.address_min,
            address_max=defaults.address_max,
        )
        request = ScanRequest(args.data_type, args.scan_mode, args.value, args.value2, options)
        session_id = self.controller.start_scan(request, Actor.AGENT)
        return ScanStartedResult(
            ok=True, session_id=session_id, state="scanning", timeout_ms=timeout_ms
        )

    def _refine_scan(self, base: BaseModel) -> BaseModel:
        args = cast(RefineScanArgs, base)
        timeout_ms = _timeout(args.timeout_ms)
        status = self.controller.scan_status()
        if status.data_type is None:
            raise ValueError("No hay un escaneo inicial cuyo tipo se pueda refinar.")
        request = ScanRequest(
            status.data_type, args.scan_mode, args.value, args.value2, ScanOptions()
        )
        session_id = self.controller.refine_scan(request, Actor.AGENT)
        return ScanStartedResult(
            ok=True, session_id=session_id, state="scanning", timeout_ms=timeout_ms
        )

    def _cancel_scan(self, base: BaseModel) -> BaseModel:
        cast(CancelScanArgs, base)
        self.controller.cancel_scan()
        return OperationResult(ok=True, message="Cancelación solicitada.")

    def _get_scan_status(self, base: BaseModel) -> BaseModel:
        cast(GetScanStatusArgs, base)
        status = self.controller.scan_status()
        return ScanStatusResult(
            ok=True,
            session_id=status.session_id,
            state=status.state.value,
            data_type=status.data_type.value if status.data_type is not None else None,
            last_mode=status.last_mode.value if status.last_mode is not None else None,
            candidates=status.candidates,
            refinements=status.refinements,
            error=_clip_optional(status.error),
        )

    def _list_scan_results(self, base: BaseModel) -> BaseModel:
        args = cast(ListScanResultsArgs, base)
        offset = max(0, args.offset or 0)
        requested_limit = 50 if args.limit is None else max(1, args.limit)
        limit = min(_MAX_ROWS, requested_limit)
        order = OrderSpec(
            column=args.sort or "address",
            descending=False if args.descending is None else args.descending,
        )
        page = self.controller.results_page(
            offset, limit, order, FilterSpec(text=args.filter_text or "")
        )
        rows = [
            ScanResultRow(
                address=row.address,
                address_hex=f"0x{row.address:016X}",
                current=_clip(row.current),
                previous=_clip(row.previous),
                data_type=row.data_type.value,
                region=_clip(row.region),
                protection=_clip(row.protection, 32),
                change_rate=row.change_rate,
                readable=row.readable,
                writable=row.writable,
            )
            for row in page.rows[:_MAX_ROWS]
        ]
        return _bounded_prefix(
            rows,
            lambda values, clipped: ScanResultsResult(
                ok=True,
                rows=values,
                offset=page.offset,
                limit=len(values),
                total=page.total,
                total_unfiltered=page.total_unfiltered,
                truncated=clipped
                or requested_limit > _MAX_ROWS
                or len(page.rows) > len(values)
                or page.offset + len(values) < page.total,
            ),
        )

    def _read_address(self, base: BaseModel) -> BaseModel:
        args = cast(ReadAddressArgs, base)
        value = self.controller.read_address(args.address, args.data_type)
        return AddressReadResult(
            ok=True,
            address=args.address,
            address_hex=f"0x{args.address:016X}",
            data_type=args.data_type.value,
            value=_clip(value),
        )

    def _add_watch(self, base: BaseModel) -> BaseModel:
        args = cast(AddWatchArgs, base)
        watch = self.controller.add_watch(
            WatchSpec(label=args.label, data_type=args.data_type, address=args.address), Actor.AGENT
        )
        return WatchAddedResult(ok=True, watch=_watch_result(watch))

    def _list_watches(self, base: BaseModel) -> BaseModel:
        cast(ListWatchesArgs, base)
        entries = self.controller.list_watches()
        watches = [_watch_result(entry) for entry in entries[:_MAX_ROWS]]
        return _bounded_prefix(
            watches,
            lambda values, clipped: WatchListResult(
                ok=True,
                watches=values,
                count=len(entries),
                truncated=clipped or len(entries) > len(values),
            ),
        )

    def _write_watch(self, base: BaseModel) -> BaseModel:
        args = cast(WriteWatchArgs, base)
        self.controller.set_watch_value(args.watch_id, args.value, Actor.AGENT)
        return OperationResult(ok=True, message="Valor escrito en la vigilancia.")

    def _freeze_watch(self, base: BaseModel) -> BaseModel:
        args = cast(FreezeWatchArgs, base)
        interval_ms = 100 if args.interval_ms is None else args.interval_ms
        self.controller.set_freeze(args.watch_id, True, args.value, interval_ms, Actor.AGENT)
        return OperationResult(ok=True, message="Vigilancia congelada.")

    def _unfreeze_watch(self, base: BaseModel) -> BaseModel:
        args = cast(UnfreezeWatchArgs, base)
        watch = _find_watch(self.controller.list_watches(), args.watch_id)
        self.controller.set_freeze(args.watch_id, False, None, watch.interval_ms, Actor.AGENT)
        return OperationResult(ok=True, message="Vigilancia descongelada.")

    def _remove_watch(self, base: BaseModel) -> BaseModel:
        args = cast(RemoveWatchArgs, base)
        self.controller.remove_watch(args.watch_id, Actor.AGENT)
        return OperationResult(ok=True, message="Vigilancia eliminada.")

    def _save_workspace(self, base: BaseModel) -> BaseModel:
        args = cast(SaveWorkspaceArgs, base)
        path = _workspace_path(args.name)
        self.controller.save_workspace(path, Actor.AGENT)
        return WorkspaceResult(ok=True, name=path.stem, message="Workspace guardado.")

    def _load_workspace(self, base: BaseModel) -> BaseModel:
        args = cast(LoadWorkspaceArgs, base)
        path = _workspace_path(args.name)
        self.controller.load_workspace(path, Actor.AGENT)
        return WorkspaceResult(ok=True, name=path.stem, message="Workspace cargado.")


def _attached_result(identity: ProcessIdentity, write_access: bool | None) -> AttachedProcessResult:
    return AttachedProcessResult(
        ok=True,
        attached=True,
        pid=identity.pid,
        name=_clip(identity.name),
        path=_clip_optional(identity.path),
        architecture=identity.architecture.value,
        write_access=write_access,
    )


def _watch_result(entry: WatchEntry) -> WatchResult:
    return WatchResult(
        id=_clip(entry.id, 64),
        label=_clip(entry.label),
        data_type=entry.data_type.value,
        address=entry.address,
        module=_clip_optional(entry.module),
        offset=entry.offset,
        interval_ms=entry.interval_ms,
        notes=_clip(entry.notes),
        frozen=entry.frozen,
        desired_value=_clip_optional(entry.desired_value),
        current_value=_clip(entry.current_value),
        last_error=_clip_optional(entry.last_error),
    )


def _find_watch(entries: list[WatchEntry], watch_id: str) -> WatchEntry:
    for entry in entries:
        if entry.id == watch_id:
            return entry
    raise ValueError("La vigilancia indicada no existe. Actualiza la lista y elige un id válido.")


def _workspace_path(name: str) -> Path:
    raw = name.strip()
    if not raw:
        raise ValueError("El nombre del workspace no puede estar vacío.")
    if ".." in raw or "/" in raw or "\\" in raw or ":" in raw:
        raise ValueError("Indica solo un nombre de workspace, no una ruta.")
    without_suffix = raw[:-5] if raw.casefold().endswith(".json") else raw
    normalized = unicodedata.normalize("NFKD", without_suffix)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", ascii_name).strip("-_").casefold()
    if not slug:
        raise ValueError("El nombre del workspace debe contener letras o números.")
    root = WORKSPACE_DIR.resolve()
    path = (root / f"{slug}.json").resolve()
    if not path.is_relative_to(root):
        raise ValueError("El workspace debe permanecer en la carpeta segura de MemPilot.")
    return path


def _timeout(value: int | None) -> int:
    timeout = _DEFAULT_TIMEOUT_MS if value is None else value
    if not 1 <= timeout <= 120_000:
        raise ValueError("El tiempo de espera debe estar entre 1 y 120000 ms.")
    return timeout


def _bounded_prefix[ItemT](
    items: list[ItemT], build: Callable[[list[ItemT], bool], BaseModel]
) -> BaseModel:
    high = len(items)
    low = 0
    best = build([], bool(items))
    while low <= high:
        middle = (low + high) // 2
        candidate = build(items[:middle], middle < len(items))
        if len(candidate.model_dump_json().encode("utf-8")) <= _MAX_JSON_BYTES:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


def _clip(text: str, limit: int = _MAX_TEXT) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _clip_optional(text: str | None, limit: int = _MAX_TEXT) -> str | None:
    return None if text is None else _clip(text, limit)


def _error_code(exc: Exception) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", type(exc).__name__).casefold()
