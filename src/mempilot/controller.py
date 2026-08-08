"""Single application facade shared by the GUI and typed agent tools."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

import numpy as np
from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, Signal, Slot

from mempilot.config.paths import repo_root
from mempilot.config.settings import Settings
from mempilot.core.backend import AccessMode, MemoryBackend, ModuleInfo, ProcessIdentity
from mempilot.core.data_types import (
    NUMERIC_TYPES,
    DataType,
    decode_value,
    encode_value,
    numpy_dtype,
    type_size,
)
from mempilot.core.exceptions import (
    InvalidAddressError,
    MemPilotError,
    NotAttachedError,
    PolicyDenied,
    ProcessExitedError,
    ScanError,
    WorkspaceError,
)
from mempilot.core.freezer import FreezeController
from mempilot.core.pointer_chain import (
    ChainResolution,
    PointerChain,
)
from mempilot.core.pointer_chain import (
    resolve_chain as resolve_pointer_chain,
)
from mempilot.core.scan_session import (
    CandidateRow,
    FilterSpec,
    OrderSpec,
    ScanSession,
    SessionState,
)
from mempilot.core.scanner import (
    CandidateSet,
    ScanEngine,
    ScanMode,
    ScanProgress,
    ScanRequest,
    UnknownSnapshot,
)
from mempilot.core.watcher import WatchEntry, WatchSpec, WatchTable, resolve_watch_address
from mempilot.services.audit_service import AuditService
from mempilot.services.workspace_service import WorkspaceModel, load_workspace, save_workspace
from mempilot.ui.workers import (
    AgentJob,
    AgentWorker,
    ProcessListWorker,
    RowRefresh,
    ScanWorker,
    ScanWorkerResult,
    ToolInvocation,
    VisibleResultRows,
    WatchScheduler,
    start_worker,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from mempilot.core.process_service import ProcessEntry, ProcessService
    from mempilot.services.workspace_service import WatchEntryModel

_LOG = logging.getLogger(__name__)


class Actor(StrEnum):
    USER = "user"
    AGENT = "agent"


class AgentPolicyBinding(Protocol):
    """Cycle-free subset of AgentPolicy required by the controller."""

    bound_identity: ProcessIdentity | None


@dataclass(slots=True)
class _LocalAgentPolicyBinding:
    bound_identity: ProcessIdentity | None = None


@dataclass(frozen=True, slots=True)
class ScanStatus:
    session_id: str | None
    state: SessionState
    data_type: DataType | None
    last_mode: ScanMode | None
    candidates: int
    progress: ScanProgress | None
    refinements: int
    error: str | None


@dataclass(frozen=True, slots=True)
class ResultsPage:
    rows: list[CandidateRow]
    offset: int
    limit: int
    total: int
    total_unfiltered: int


class AppController(QObject):
    """Only facade allowed to coordinate process memory and application state."""

    attached = Signal(object)
    detached = Signal(str)
    process_lost = Signal(int)
    scan_started = Signal(object)
    scan_progress = Signal(object)
    scan_finished = Signal(object)
    scan_failed = Signal(str)
    scan_cancelled = Signal()
    watches_changed = Signal()
    watch_values = Signal(object)
    audit_appended = Signal(object)
    agent_event = Signal(object)
    confirmation_required = Signal(object)
    autonomous_changed = Signal(bool, int, int)
    processes_listed = Signal(object)
    process_list_failed = Signal(str)
    result_values = Signal(object)
    watch_write_error = Signal(str)
    _scheduler_reconfigure_requested = Signal()
    _scheduler_rows_requested = Signal(object)

    def __init__(
        self,
        backend: MemoryBackend | None = None,
        *,
        process_service: ProcessService | None = None,
        audit_service: AuditService | None = None,
        settings: Settings | None = None,
        agent_policy: AgentPolicyBinding | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if backend is None:
            from mempilot.core.win32_backend import Win32MemoryBackend

            backend = Win32MemoryBackend()
        self._backend = backend
        self._process_service = process_service
        self._audit = audit_service or AuditService()
        self._settings = settings or Settings()
        self._agent_policy = agent_policy or _LocalAgentPolicyBinding()
        self._engine = ScanEngine(self._backend)
        self._watches = WatchTable(self._watches_did_change)
        self._freezer = FreezeController(self._backend, self._audit)
        self._session: ScanSession | None = None
        self._last_progress: ScanProgress | None = None
        self._active_scan_request: ScanRequest | None = None
        self._scan_is_refinement = False
        self._pointer_chains: dict[str, PointerChain] = {}
        self._workspace_created_at: datetime | None = None
        initial_identity = self._backend.identity
        self._known_identities: dict[int, ProcessIdentity] = (
            {initial_identity.pid: initial_identity} if initial_identity is not None else {}
        )
        self._scan_worker: ScanWorker | None = None
        self._scan_thread: QThread | None = None
        self._scan_cancel: threading.Event | None = None
        self._scheduler: WatchScheduler | None = None
        self._scheduler_thread: QThread | None = None
        self._agent_worker: AgentWorker | None = None
        self._agent_thread: QThread | None = None
        self._agent_cancel: threading.Event | None = None
        self._process_workers: dict[int, tuple[ProcessListWorker, QThread, threading.Event]] = {}
        self._shutting_down = False
        self._audit.audit_appended.connect(self.audit_appended.emit)

    def list_processes(self, query: str = "", include_system: bool = False) -> list[ProcessEntry]:
        return self._get_process_service().list_processes(query, include_system)

    def request_processes(self, query: str = "", include_system: bool = False) -> QThread:
        """Relaunch cancellable process enumeration for GUI callers."""
        cancel = threading.Event()
        worker = ProcessListWorker(self._get_process_service(), query, include_system, cancel)
        worker.result.connect(self.processes_listed.emit)
        worker.failed.connect(self._on_process_list_failed)
        thread = start_worker(worker, self._worker_lifecycle_finished)
        self._process_workers[id(thread)] = (worker, thread, cancel)
        thread.finished.connect(self._on_process_thread_finished)
        return thread

    def attach(self, pid: int, write_access: bool, actor: Actor) -> ProcessIdentity:
        identity = self._identity_for_pid(pid)
        bound = self._agent_policy.bound_identity
        if actor is Actor.AGENT and bound is not None and not identity.matches(bound):
            raise PolicyDenied(
                "El agente está vinculado a otro proceso. "
                "Pide al usuario que seleccione el proceso."
            )
        if self._backend.is_open:
            self._detach_internal("Se cambió el proceso adjunto.", actor)
        mode = AccessMode.READ_WRITE if write_access else AccessMode.READ
        self._backend.open(identity, mode)
        opened_identity = self._backend.identity
        if opened_identity is None or not opened_identity.matches(identity):
            self._backend.close()
            raise ProcessExitedError(
                "El proceso cambió mientras se abría. Actualiza la lista y vuelve a intentarlo."
            )
        self._known_identities[identity.pid] = identity
        self._agent_policy.bound_identity = identity
        self._session = None
        self._last_progress = None
        self._start_scheduler()
        self._audit.record(
            actor.value,
            "attach",
            f"pid:{identity.pid}",
            f"{identity.name}; modo={mode.value}",
            "ok",
        )
        self.attached.emit(identity)
        return identity

    def detach(self, reason: str, actor: Actor = Actor.USER) -> None:
        if not self._backend.is_open:
            return
        identity = self._backend.identity
        if self._backend.is_alive():
            self._require_attached(actor)
        elif actor is Actor.AGENT:
            self._require_agent_identity(identity)
        self._detach_internal(reason, actor)

    def attached_identity(self) -> ProcessIdentity | None:
        return self._backend.identity if self._backend.is_open else None

    def list_modules(self, actor: Actor = Actor.USER) -> list[ModuleInfo]:
        """Return modules for the attached process through the guarded facade."""
        self._require_attached(actor)
        return self._backend.modules()

    def start_scan(self, request: ScanRequest, actor: Actor) -> str:
        identity = self._require_attached(actor)
        request.validate()
        self._ensure_no_active_scan()
        session = ScanSession(
            identity=identity, data_type=request.data_type, options=request.options
        )
        session.state = SessionState.SCANNING
        self._session = session
        self._last_progress = None
        self._active_scan_request = request
        self._scan_is_refinement = False
        self._scheduler_rows_requested.emit(VisibleResultRows(session.session_id, ()))
        self._launch_scan_worker(request, None)
        self._audit.record(
            actor.value,
            "scan_start",
            f"pid:{identity.pid}",
            f"tipo={request.data_type.value}; modo={request.mode.value}",
            "iniciado",
        )
        self.scan_started.emit(request)
        return session.session_id

    def refine_scan(self, request: ScanRequest, actor: Actor) -> str:
        identity = self._require_attached(actor)
        request.validate()
        self._ensure_no_active_scan()
        session = self._session
        if session is None or session.result is None or session.state is not SessionState.READY:
            raise ScanError(
                "No hay un escaneo listo para refinar. Ejecuta primero un escaneo inicial."
            )
        if not session.identity.matches(identity):
            raise ScanError("La sesión pertenece a otro proceso. Inicia un nuevo escaneo.")
        if request.data_type is not session.data_type:
            raise ScanError("El tipo del refinamiento debe coincidir con el escaneo inicial.")
        session.state = SessionState.SCANNING
        self._last_progress = None
        self._active_scan_request = request
        self._scan_is_refinement = True
        self._scheduler_rows_requested.emit(VisibleResultRows(session.session_id, ()))
        self._launch_scan_worker(request, session.result)
        self._audit.record(
            actor.value,
            "scan_refine",
            f"pid:{identity.pid}",
            f"modo={request.mode.value}; antes={session.total()}",
            "iniciado",
        )
        self.scan_started.emit(request)
        return session.session_id

    def cancel_scan(self) -> None:
        if self._scan_cancel is not None:
            self._scan_cancel.set()

    def reset_scan(self) -> None:
        """Discard the current scan session while keeping the process attached."""
        self._require_attached(Actor.USER)
        if self._session is not None and self._session.state is SessionState.SCANNING:
            raise ScanError("Cancela el escaneo en curso antes de reiniciar la sesión.")
        self._session = None
        self._last_progress = None
        self._active_scan_request = None
        self._scan_is_refinement = False
        self._scheduler_rows_requested.emit(VisibleResultRows("", ()))
        self.result_values.emit({})

    def scan_status(self) -> ScanStatus:
        session = self._session
        if session is None:
            return ScanStatus(None, SessionState.NEW, None, None, 0, None, 0, None)
        return ScanStatus(
            session.session_id,
            session.state,
            session.data_type,
            session.last_mode,
            session.total(),
            self._last_progress,
            len(session.history),
            session.error,
        )

    def results_page(
        self, offset: int, limit: int, order: OrderSpec, filt: FilterSpec
    ) -> ResultsPage:
        self._require_attached(Actor.USER)
        session = self._session
        if session is None or session.state is not SessionState.READY:
            return ResultsPage([], offset, limit, 0, 0)
        rows = session.page(offset, limit, order, filt)
        return ResultsPage(
            rows, offset, limit, self._filtered_total(session, filt), session.total()
        )

    def set_visible_results(self, rows: Sequence[CandidateRow]) -> None:
        session = self._session
        if session is not None:
            visible = VisibleResultRows(
                session.session_id,
                tuple(
                    (row.address, row.data_type)
                    for row in rows[: self._settings.ui.results_page_size]
                ),
            )
            self._scheduler_rows_requested.emit(visible)

    def read_address(self, address: int, data_type: DataType) -> str:
        self._require_attached(Actor.USER)
        if address < 0:
            raise InvalidAddressError("La dirección no puede ser negativa.")
        return decode_value(data_type, self._backend.read(address, self._read_size(data_type)))

    def write_address(self, address: int, data_type: DataType, value: str, actor: Actor) -> None:
        identity = self._require_attached(actor)
        if address < 0:
            raise InvalidAddressError("La dirección no puede ser negativa.")
        encoded = encode_value(data_type, value)
        written = self._backend.write(address, encoded)
        if written != len(encoded):
            raise InvalidAddressError(
                f"Solo se escribieron {written} de {len(encoded)} bytes. Actualiza la dirección."
            )
        self._audit.record(
            actor.value,
            "write",
            f"0x{address:016X}",
            f"pid={identity.pid}; tipo={data_type.value}; valor={value}",
            "ok",
        )

    def add_watch(self, spec: WatchSpec, actor: Actor) -> WatchEntry:
        identity = self._require_attached(actor)
        preview = WatchEntry.from_spec(spec)
        address, error = resolve_watch_address(preview, self._backend, self._safe_modules())
        if address is None:
            raise InvalidAddressError(error or "No se pudo resolver la dirección de vigilancia.")
        entry = self._watches.add(spec)
        if entry.chain is not None:
            self._pointer_chains[entry.chain.id] = entry.chain
        self._audit.record(
            actor.value,
            "watch_add",
            entry.id,
            f"pid={identity.pid}; dirección=0x{address:016X}; tipo={entry.data_type.value}",
            "ok",
        )
        return entry

    def list_watches(self) -> list[WatchEntry]:
        return self._watches.entries()

    def update_watch(
        self,
        watch_id: str,
        *,
        label: str | None = None,
        desired_value: str | None = None,
        interval_ms: int | None = None,
        notes: str | None = None,
        actor: Actor = Actor.USER,
    ) -> None:
        """Update editable watch metadata through the guarded facade."""
        identity = self._require_attached(actor)
        entry = self._watches.get(watch_id)
        if desired_value is not None:
            encode_value(entry.data_type, desired_value)
        updated = self._watches.update(
            watch_id,
            label=label,
            desired_value=desired_value,
            interval_ms=interval_ms,
            notes=notes,
        )
        self._audit.record(
            actor.value,
            "watch_update",
            watch_id,
            f"pid={identity.pid}; etiqueta={updated.label}; intervalo={updated.interval_ms}ms",
            "ok",
        )

    def remove_watch(self, watch_id: str, actor: Actor) -> None:
        identity = self._require_attached(actor)
        entry = self._watches.remove(watch_id)
        self._audit.record(
            actor.value,
            "watch_remove",
            watch_id,
            f"pid={identity.pid}; etiqueta={entry.label}",
            "ok",
        )

    def set_watch_value(self, watch_id: str, value: str, actor: Actor) -> None:
        identity = self._require_attached(actor)
        entry = self._watches.get(watch_id)
        address, error = resolve_watch_address(entry, self._backend, self._safe_modules())
        if address is None:
            raise InvalidAddressError(error or "No se pudo resolver la vigilancia.")
        encoded = encode_value(entry.data_type, value)
        written = self._backend.write(address, encoded)
        if written != len(encoded):
            raise InvalidAddressError("La escritura de la vigilancia quedó incompleta.")
        self._watches.set_written_value(watch_id, value)
        self._audit.record(
            actor.value,
            "watch_write",
            watch_id,
            f"pid={identity.pid}; dirección=0x{address:016X}; valor={value}",
            "ok",
        )

    def set_freeze(
        self, watch_id: str, frozen: bool, value: str | None, interval_ms: int, actor: Actor
    ) -> None:
        identity = self._require_attached(actor)
        entry = self._watches.get(watch_id)
        desired = value if value is not None else entry.desired_value
        if frozen:
            if desired is None:
                raise ValueError("Indica un valor deseado antes de congelar la vigilancia.")
            encode_value(entry.data_type, desired)
        updated = self._watches.set_freeze(
            watch_id, frozen=frozen, desired_value=desired, interval_ms=interval_ms
        )
        self._freezer.invalidate_cache()
        self._audit.record(
            actor.value,
            "freeze_on" if frozen else "freeze_off",
            watch_id,
            f"pid={identity.pid}; valor={updated.desired_value}; intervalo={interval_ms}ms",
            "ok",
        )

    def resolve_chain(self, chain: PointerChain) -> ChainResolution:
        self._require_attached(Actor.USER)
        return resolve_pointer_chain(chain, self._backend, self._safe_modules())

    def save_workspace(self, path: Path, actor: Actor) -> None:
        identity = self._require_attached(actor)
        now = datetime.now(UTC)
        for entry in self._watches.entries():
            if entry.chain is not None:
                self._pointer_chains[entry.chain.id] = entry.chain
        models = cast("list[WatchEntryModel]", self._watches.to_models())
        workspace = WorkspaceModel(
            created_at=self._workspace_created_at or now,
            updated_at=now,
            process_name=identity.name,
            process_path=identity.path,
            architecture=identity.architecture,
            watches=models,
            pointer_chains=list(self._pointer_chains.values()),
            watch_refresh_ms=self._settings.ui.watch_refresh_ms,
            results_refresh_ms=self._settings.ui.results_refresh_ms,
        )
        save_workspace(path, workspace)
        self._workspace_created_at = workspace.created_at
        self._audit.record(actor.value, "workspace_save", str(path), identity.name, "ok")

    def load_workspace(self, path: Path, actor: Actor) -> None:
        identity = self._require_attached(actor)
        workspace = load_workspace(path)
        if workspace.process_name.casefold() != identity.name.casefold():
            raise WorkspaceError(
                f"El workspace pertenece a {workspace.process_name!r}; "
                f"el proceso adjunto es {identity.name!r}."
            )
        if workspace.architecture is not identity.architecture:
            raise WorkspaceError(
                "La arquitectura del workspace no coincide con el proceso adjunto."
            )
        restored = WatchTable.from_models(workspace.watches, workspace.pointer_chains)
        self._watches.replace_all(restored.entries())
        self._pointer_chains = {chain.id: chain for chain in workspace.pointer_chains}
        self._workspace_created_at = workspace.created_at
        self._freezer.invalidate_cache()
        self._audit.record(actor.value, "workspace_load", str(path), identity.name, "ok")

    def launch_memory_lab(self) -> int:
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--memory-lab"]
        else:
            command = [sys.executable, str(repo_root() / "tools" / "memory_lab.py")]
        process = subprocess.Popen(
            command, creationflags=int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        )
        self._audit.record("user", "memory_lab_launch", f"pid:{process.pid}", "", "ok")
        return int(process.pid)

    def start_agent_job(
        self,
        job: AgentJob
        | Callable[[threading.Event, Callable[[str, str, float | None], str]], object],
        tool_handler: Callable[[ToolInvocation], None] | None = None,
        *,
        tool_timeout_s: float | None = None,
    ) -> QThread:
        if self._agent_thread is not None and self._agent_thread.isRunning():
            raise RuntimeError("Ya hay una operación del agente en curso.")
        cancel = threading.Event()
        worker = AgentWorker(
            job,
            cancel,
            tool_timeout_s=tool_timeout_s or self._settings.ai.confirmation_timeout_s + 60.0,
        )
        if tool_handler is not None:
            worker.tool_requested.connect(tool_handler)
        worker.activity.connect(self.agent_event.emit)
        worker.result.connect(self.agent_event.emit)
        worker.failed.connect(self._on_agent_failed)
        thread = start_worker(worker, self._worker_lifecycle_finished)
        self._agent_worker, self._agent_thread, self._agent_cancel = worker, thread, cancel
        thread.finished.connect(self._on_agent_thread_finished)
        return thread

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        try:
            self._stop_scan_worker(5000)
            self._stop_process_workers(5000)
            self._stop_agent_worker(5000)
            self._stop_scheduler(5000)
            self._backend.close()
            self._audit.flush()
        finally:
            self._shutting_down = False

    def _require_attached(self, actor: Actor) -> ProcessIdentity:
        if not self._backend.is_open or self._backend.identity is None:
            raise NotAttachedError()
        identity = self._backend.identity
        assert identity is not None
        if not self._backend.is_alive():
            pid = identity.pid
            self.process_lost.emit(pid)
            self._detach_internal("El proceso terminó y MemPilot se desacopló.", Actor.USER)
            raise ProcessExitedError(
                f"El proceso PID {pid} terminó. Selecciona otro proceso para continuar."
            )
        if actor is Actor.AGENT:
            self._require_agent_identity(identity)
        return identity

    def _require_agent_identity(self, identity: ProcessIdentity | None) -> None:
        bound = self._agent_policy.bound_identity
        if identity is None or bound is None or not identity.matches(bound):
            raise PolicyDenied(
                "El proceso adjunto no coincide con la identidad autorizada para el agente. "
                "Pide al usuario que vuelva a seleccionarlo."
            )

    def _identity_for_pid(self, pid: int) -> ProcessIdentity:
        known = self._known_identities.get(pid)
        if known is not None:
            return known
        identity = self._get_process_service().identity(pid)
        self._known_identities[pid] = identity
        return identity

    def _get_process_service(self) -> ProcessService:
        if self._process_service is None:
            from mempilot.core.process_service import ProcessService

            self._process_service = ProcessService()
        return self._process_service

    def _detach_internal(self, reason: str, actor: Actor) -> None:
        identity = self._backend.identity
        self._stop_scan_worker(5000)
        self._stop_scheduler(5000)
        self._backend.close()
        self._session = None
        self._last_progress = None
        self._active_scan_request = None
        self._agent_policy.bound_identity = None
        if identity is not None:
            self._audit.record(actor.value, "detach", f"pid:{identity.pid}", reason, "ok")
        self.detached.emit(reason)

    def _launch_scan_worker(
        self, request: ScanRequest, previous: CandidateSet | UnknownSnapshot | None
    ) -> None:
        cancel = threading.Event()
        worker = ScanWorker(self._engine, request, cancel, previous)
        worker.progress.connect(self._on_scan_progress)
        worker.completed.connect(self._on_scan_completed)
        worker.failed.connect(self._on_scan_failed)
        worker.cancelled.connect(self._on_scan_cancelled)
        thread = start_worker(worker, self._worker_lifecycle_finished)
        self._scan_worker, self._scan_thread, self._scan_cancel = worker, thread, cancel
        thread.finished.connect(self._on_scan_thread_finished)

    def _ensure_no_active_scan(self) -> None:
        if self._scan_thread is not None and self._scan_thread.isRunning():
            raise ScanError("Ya hay un escaneo en curso. Cancélalo antes de iniciar otro.")

    @Slot(object)
    def _on_scan_progress(self, progress: object) -> None:
        if isinstance(progress, ScanProgress):
            self._last_progress = progress
            self.scan_progress.emit(progress)

    @Slot(object)
    def _on_scan_completed(self, payload: object) -> None:
        if not isinstance(payload, ScanWorkerResult):
            return
        session, request = self._session, self._active_scan_request
        if session is None or request is None or session.state is not SessionState.SCANNING:
            return
        if self._scan_is_refinement:
            if not isinstance(payload.result, CandidateSet):
                self._on_scan_failed(
                    ScanError("El refinamiento devolvió un resultado incompatible.")
                )
                return
            session.set_refined_result(payload.result, request, duration_s=payload.duration_s)
        else:
            try:
                regions = self._engine.select_regions(request.options)
            except Exception:
                regions = []
            session.set_first_result(
                payload.result,
                request,
                regions_scanned=payload.regions_scanned,
                bytes_scanned=payload.bytes_scanned,
                duration_s=payload.duration_s,
                memory_regions=regions,
            )
        self._audit.record(
            "system",
            "scan_finish",
            session.session_id,
            f"candidatos={session.total()}; duración={payload.duration_s:.3f}s",
            "ok",
        )
        self.scan_finished.emit(session)

    @Slot(object)
    def _on_scan_failed(self, error: object) -> None:
        exc = error if isinstance(error, Exception) else RuntimeError(str(error))
        _LOG.error("Scan worker failed", exc_info=(type(exc), exc, exc.__traceback__))
        message = exc.user_message() if isinstance(exc, MemPilotError) else str(exc)
        if not message:
            message = "El escaneo falló. Revisa el proceso y vuelve a intentarlo."
        if self._session is not None:
            self._session.state, self._session.error = SessionState.ERROR, message
        self._audit.record("system", "scan_error", "scan", message, "error")
        self.scan_failed.emit(message)

    @Slot()
    def _on_scan_cancelled(self) -> None:
        if self._session is not None and self._session.state is SessionState.SCANNING:
            self._session.state = SessionState.CANCELLED
        self._audit.record("system", "scan_cancel", "scan", "", "cancelado")
        self.scan_cancelled.emit()

    @Slot()
    def _on_scan_thread_finished(self) -> None:
        self._scan_worker = self._scan_thread = self._scan_cancel = self._active_scan_request = None
        self._scan_is_refinement = False

    def _start_scheduler(self) -> None:
        if self._scheduler_thread is not None and self._scheduler_thread.isRunning():
            self._scheduler_reconfigure_requested.emit()
            return
        scheduler = WatchScheduler(
            self._backend,
            self._watches,
            self._freezer,
            default_interval_ms=self._settings.ui.watch_refresh_ms,
            results_refresh_ms=self._settings.ui.results_refresh_ms,
            results_page_size=self._settings.ui.results_page_size,
        )
        scheduler.values.connect(self._on_watch_values)
        scheduler.row_values.connect(self.result_values.emit)
        scheduler.row_updates.connect(self._on_row_updates)
        scheduler.process_gone.connect(self._on_scheduler_process_gone)
        scheduler.write_error.connect(self._on_watch_write_error)
        self._scheduler_reconfigure_requested.connect(scheduler.reconfigure)
        self._scheduler_rows_requested.connect(scheduler.set_visible_rows)
        thread = start_worker(scheduler, self._worker_lifecycle_finished)
        self._scheduler, self._scheduler_thread = scheduler, thread
        thread.finished.connect(self._on_scheduler_thread_finished)

    @Slot(object)
    def _on_watch_values(self, values: object) -> None:
        self.watch_values.emit(values)

    @Slot(object)
    def _on_row_updates(self, raw_updates: object) -> None:
        if not isinstance(raw_updates, dict):
            return
        session = self._session
        if session is None or not isinstance(session.result, CandidateSet):
            return
        result = session.result
        for raw_address, update in raw_updates.items():
            if (
                not isinstance(raw_address, int)
                or not isinstance(update, RowRefresh)
                or update.session_id != session.session_id
                or update.data_type is not session.data_type
            ):
                continue
            positions = np.flatnonzero(result.addresses == raw_address)
            if not positions.size:
                continue
            index = int(positions[0])
            session._change_rates[raw_address] = update.change_rate
            if isinstance(result.values, np.ndarray):
                result.values[index] = np.frombuffer(
                    update.raw, dtype=numpy_dtype(session.data_type), count=1
                )[0]
            else:
                result.values[index] = update.raw

    @Slot()
    def _on_scheduler_process_gone(self) -> None:
        identity = self._backend.identity
        if identity is not None:
            self.process_lost.emit(identity.pid)
            self._detach_internal("El proceso terminó y MemPilot se desacopló.", Actor.USER)

    @Slot(str)
    def _on_watch_write_error(self, message: str) -> None:
        self.watch_write_error.emit(message)

    @Slot()
    def _on_scheduler_thread_finished(self) -> None:
        self._scheduler = self._scheduler_thread = None

    def _stop_scan_worker(self, wait_ms: int) -> None:
        if self._scan_cancel is not None:
            self._scan_cancel.set()
        thread = self._scan_thread
        if thread is not None and thread.isRunning() and not thread.wait(wait_ms):
            _LOG.error("El worker de escaneo no terminó dentro de %d ms", wait_ms)

    def _stop_scheduler(self, wait_ms: int) -> None:
        thread = self._scheduler_thread
        scheduler = self._scheduler
        if thread is None:
            return
        if thread.isRunning() and scheduler is not None:
            QMetaObject.invokeMethod(
                scheduler,
                "stop",
                Qt.ConnectionType.BlockingQueuedConnection,
            )
            thread.quit()
            if not thread.wait(wait_ms):
                _LOG.error("El planificador no terminó dentro de %d ms", wait_ms)
        if not thread.isRunning():
            self._scheduler = self._scheduler_thread = None

    def _stop_agent_worker(self, wait_ms: int) -> None:
        if self._agent_cancel is not None:
            self._agent_cancel.set()
        thread = self._agent_thread
        if thread is not None and thread.isRunning() and not thread.wait(wait_ms):
            _LOG.error("El worker del agente no terminó dentro de %d ms", wait_ms)

    def _stop_process_workers(self, wait_ms: int) -> None:
        workers = list(self._process_workers.values())
        for _worker, _thread, cancel in workers:
            cancel.set()
        for _worker, thread, _cancel in workers:
            if thread.isRunning() and not thread.wait(wait_ms):
                _LOG.error("Un worker de procesos no terminó dentro de %d ms", wait_ms)

    @Slot()
    def _on_agent_thread_finished(self) -> None:
        self._agent_worker = self._agent_thread = self._agent_cancel = None

    @Slot(object)
    def _on_agent_failed(self, error: object) -> None:
        self.agent_event.emit(error)

    @Slot(object)
    def _on_process_list_failed(self, error: object) -> None:
        self.process_list_failed.emit(
            error.user_message() if isinstance(error, MemPilotError) else str(error)
        )

    @Slot()
    def _on_process_thread_finished(self) -> None:
        sender = self.sender()
        if isinstance(sender, QThread):
            self._process_workers.pop(id(sender), None)

    @Slot()
    def _worker_lifecycle_finished(self) -> None:
        pass

    def _watches_did_change(self) -> None:
        self.watches_changed.emit()
        self._scheduler_reconfigure_requested.emit()

    def _safe_modules(self) -> list[Any]:
        try:
            return self._backend.modules()
        except Exception as exc:
            _LOG.warning("No se pudieron enumerar los módulos: %s", exc)
            return []

    @staticmethod
    def _read_size(data_type: DataType) -> int:
        if data_type in NUMERIC_TYPES:
            return type_size(data_type)
        return 256 if data_type in {DataType.STRING_UTF8, DataType.STRING_UTF16} else 16

    @staticmethod
    def _filtered_total(session: ScanSession, filt: FilterSpec) -> int:
        if not isinstance(session.result, CandidateSet):
            return 0
        result = session.result
        selected = np.ones(len(result), dtype=np.bool_)
        if filt.address_min is not None:
            selected &= result.addresses >= filt.address_min
        if filt.address_max is not None:
            selected &= result.addresses <= filt.address_max
        regions: Any = None
        if filt.module:
            regions = session._region_labels(result.addresses)
            selected &= np.char.startswith(np.char.lower(regions), filt.module.casefold())
        if filt.text:
            current = session._display_values(result.values)
            if regions is None:
                regions = session._region_labels(result.addresses)
            address_text = np.asarray([f"0x{int(address):016X}" for address in result.addresses])
            haystack = np.char.add(np.char.add(address_text, " "), current)
            haystack = np.char.add(np.char.add(haystack, " "), regions)
            selected &= np.char.find(np.char.lower(haystack), filt.text.casefold()) >= 0
        return int(np.count_nonzero(selected))
