"""Qt worker objects for every non-GUI execution lane."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, QTimer, Signal, Slot

from mempilot.core.backend import MemoryBackend, ModuleInfo
from mempilot.core.data_types import NUMERIC_TYPES, DataType, decode_value, encode_value, type_size
from mempilot.core.freezer import FreezeController, FreezeTarget
from mempilot.core.scanner import (
    CandidateSet,
    ScanEngine,
    ScanProgress,
    ScanRequest,
    UnknownSnapshot,
)
from mempilot.core.watcher import WatchEntry, WatchTable, resolve_watch_address

if TYPE_CHECKING:
    from mempilot.core.process_service import ProcessService


class _BaseWorker(QObject):
    """Common lifecycle signal used by the approved QObject/QThread pattern."""

    finished = Signal()

    @Slot()
    def run(self) -> None:
        """Execute the worker body."""
        raise NotImplementedError


class ProcessListWorker(_BaseWorker):
    """Enumerate processes away from the GUI thread."""

    result = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        service: ProcessService,
        query: str = "",
        include_system: bool = False,
        cancel: threading.Event | None = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._query = query
        self._include_system = include_system
        self.cancel_event = cancel or threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            if self.cancel_event.is_set():
                self.cancelled.emit()
                return
            processes = self._service.list_processes(self._query, self._include_system)
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.result.emit(processes)
        except Exception as exc:
            self.failed.emit(exc)
        finally:
            self.finished.emit()


@dataclass(frozen=True, slots=True)
class ScanWorkerResult:
    """Scan output plus measured metadata needed by ScanSession."""

    result: CandidateSet | UnknownSnapshot
    duration_s: float
    regions_scanned: int
    bytes_scanned: int


class ScanWorker(_BaseWorker):
    """Run one first scan or refinement with direct Event cancellation."""

    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        engine: ScanEngine,
        request: ScanRequest,
        cancel: threading.Event,
        previous: CandidateSet | UnknownSnapshot | None = None,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._request = request
        self._previous = previous
        self.cancel_event = cancel
        self._last_progress: ScanProgress | None = None

    @Slot()
    def run(self) -> None:
        started = time.monotonic()
        try:
            regions = self._engine.select_regions(self._request.options)
            if self._previous is None:
                result = self._engine.first_scan(
                    self._request,
                    self.cancel_event,
                    self._on_progress,
                )
                regions_scanned = len(regions)
                bytes_scanned = (
                    result.bytes_captured
                    if isinstance(result, UnknownSnapshot)
                    else sum(region.size for region in regions)
                )
            else:
                result = self._engine.refine(
                    self._previous,
                    self._request,
                    self.cancel_event,
                    self._on_progress,
                )
                regions_scanned = (
                    self._last_progress.regions_done if self._last_progress is not None else 0
                )
                bytes_scanned = (
                    self._last_progress.bytes_done if self._last_progress is not None else 0
                )
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.completed.emit(
                    ScanWorkerResult(
                        result=result,
                        duration_s=time.monotonic() - started,
                        regions_scanned=regions_scanned,
                        bytes_scanned=bytes_scanned,
                    )
                )
        except Exception as exc:
            from mempilot.core.exceptions import ScanCancelled

            if isinstance(exc, ScanCancelled) or self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(exc)
        finally:
            self.finished.emit()

    def _on_progress(self, progress: ScanProgress) -> None:
        self._last_progress = progress
        self.progress.emit(progress)


@dataclass(slots=True)
class ToolInvocation:
    """Cross-thread request fulfilled by a slot on the GUI thread."""

    name: str
    arguments_json: str
    done: threading.Event = field(default_factory=threading.Event)
    result_json: str = ""


class AgentJob(Protocol):
    """Minimal orchestrator job accepted by AgentWorker."""

    def run(
        self,
        cancel: threading.Event,
        request_tool: Callable[[str, str, float | None], str],
    ) -> object: ...


class AgentWorker(_BaseWorker):
    """Run provider/tool loops while executing tool calls on the GUI thread."""

    tool_requested = Signal(object)
    activity = Signal(object)
    result = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        job: AgentJob
        | Callable[[threading.Event, Callable[[str, str, float | None], str]], object],
        cancel: threading.Event | None = None,
        *,
        tool_timeout_s: float = 180.0,
    ) -> None:
        super().__init__()
        if tool_timeout_s <= 0:
            raise ValueError("El tiempo de espera de herramientas debe ser positivo.")
        self._job = job
        self.cancel_event = cancel or threading.Event()
        self._tool_timeout_s = tool_timeout_s

    @Slot()
    def run(self) -> None:
        try:
            if self.cancel_event.is_set():
                self.cancelled.emit()
                return
            runner = self._job.run if hasattr(self._job, "run") else self._job
            result = runner(self.cancel_event, self.request_tool)
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.result.emit(result)
        except Exception as exc:
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(exc)
        finally:
            self.finished.emit()

    def request_tool(
        self,
        name: str,
        arguments_json: str,
        timeout_s: float | None = None,
    ) -> str:
        """Emit a tool request and wait interruptibly for the GUI-thread decision."""
        invocation = ToolInvocation(name=name, arguments_json=arguments_json)
        self.tool_requested.emit(invocation)
        deadline = time.monotonic() + (timeout_s or self._tool_timeout_s)
        while not invocation.done.wait(0.05):
            if self.cancel_event.is_set():
                return json.dumps(
                    {"ok": False, "error": "Operación del agente cancelada."},
                    ensure_ascii=False,
                )
            if time.monotonic() >= deadline:
                return json.dumps(
                    {"ok": False, "error": "La herramienta agotó el tiempo de espera."},
                    ensure_ascii=False,
                )
        return invocation.result_json


@dataclass(frozen=True, slots=True)
class VisibleResultRows:
    """Current results-page addresses consumed by the shared scheduler."""

    session_id: str
    rows: tuple[tuple[int, DataType], ...]


@dataclass(frozen=True, slots=True)
class RowRefresh:
    """Raw and formatted row refresh used to update ScanSession in the GUI thread."""

    data_type: DataType
    raw: bytes
    text: str
    change_rate: float
    session_id: str


@dataclass(frozen=True, slots=True)
class _ReadTarget:
    key: tuple[str, str | int]
    address: int
    size: int


class WatchScheduler(_BaseWorker):
    """Single timer for watches, freezing, and visible result-page refreshes."""

    values = Signal(object)
    row_values = Signal(object)
    row_updates = Signal(object)
    process_gone = Signal()
    write_error = Signal(str)

    def __init__(
        self,
        backend: MemoryBackend,
        watches: WatchTable,
        freezer: FreezeController,
        *,
        default_interval_ms: int = 100,
        results_refresh_ms: int = 500,
        results_page_size: int = 1000,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._watches = watches
        self._freezer = freezer
        self._default_interval_ms = self._bounded_interval(default_interval_ms)
        self._results_refresh_ms = self._bounded_interval(results_refresh_ms)
        if results_page_size < 1:
            raise ValueError("El tamaño de página de resultados debe ser positivo.")
        self._results_page_size = results_page_size
        self._timer: QTimer | None = None
        self._modules: list[ModuleInfo] = []
        self._visible = VisibleResultRows("", ())
        self._last_watch: dict[str, float] = {}
        self._last_results = 0.0
        self._row_previous: dict[int, str] = {}
        self._row_rates: dict[int, float] = {}
        self._stopped = False

    @Slot()
    def run(self) -> None:
        if self._stopped:
            self.finished.emit()
            return
        if self._timer is not None:
            return
        self._timer = QTimer(self)
        self._timer.setTimerType(self._timer.timerType())
        self._timer.timeout.connect(self.tick)
        self.reconfigure()
        self._timer.start()

    @Slot()
    def reconfigure(self) -> None:
        """Recompute the one timer interval from active work."""
        intervals = [entry.interval_ms for entry in self._watches.entries()]
        intervals.append(
            self._results_refresh_ms if self._visible.rows else self._default_interval_ms
        )
        interval = self._bounded_interval(min(intervals, default=self._default_interval_ms))
        if self._timer is not None:
            self._timer.setInterval(interval)

    @Slot(object)
    def set_visible_rows(self, visible: object) -> None:
        """Replace the bounded page refreshed on subsequent ticks."""
        if not isinstance(visible, VisibleResultRows):
            raise TypeError("Se esperaba una página visible de resultados.")
        self._visible = VisibleResultRows(
            visible.session_id,
            visible.rows[: self._results_page_size],
        )
        active_addresses = {address for address, _data_type in self._visible.rows}
        self._row_previous = {
            address: value
            for address, value in self._row_previous.items()
            if address in active_addresses
        }
        self._row_rates = {
            address: value
            for address, value in self._row_rates.items()
            if address in active_addresses
        }
        self.reconfigure()

    @Slot()
    def tick(self) -> None:
        if not self._backend.is_open:
            return
        if not self._backend.is_alive():
            self.process_gone.emit()
            self.stop()
            return
        now = time.monotonic()
        if not self._modules:
            try:
                self._modules = self._backend.modules()
            except Exception:
                self._modules = []
        due_entries = [
            entry
            for entry in self._watches.entries()
            if now - self._last_watch.get(entry.id, 0.0) >= entry.interval_ms / 1000.0
        ]
        rows_due = bool(self._visible.rows) and (
            now - self._last_results >= self._results_refresh_ms / 1000.0
        )
        targets: list[_ReadTarget] = []
        resolved: dict[str, tuple[WatchEntry, int]] = {}
        watch_errors: dict[str, str] = {}
        for entry in due_entries:
            self._last_watch[entry.id] = now
            address, error = resolve_watch_address(entry, self._backend, self._modules)
            if address is None:
                watch_errors[entry.id] = error or "No se pudo resolver la dirección."
                continue
            size = self._watch_size(entry)
            resolved[entry.id] = (entry, address)
            targets.append(_ReadTarget(("watch", entry.id), address, size))
        if rows_due:
            self._last_results = now
            for address, data_type in self._visible.rows:
                targets.append(_ReadTarget(("row", address), address, self._row_size(data_type)))
        raw_by_key = self._read_grouped(targets)
        values: dict[str, str] = {}
        freeze_targets: list[FreezeTarget] = []
        for entry in due_entries:
            pair = resolved.get(entry.id)
            raw = raw_by_key.get(("watch", entry.id))
            if pair is None or raw is None:
                error = watch_errors.get(entry.id, "No se pudo leer la dirección vigilada.")
                self._watches.update_runtime(entry.id, entry.current_value, error)
                continue
            _stored_entry, address = pair
            try:
                text = decode_value(entry.data_type, raw)
            except Exception as exc:
                self._watches.update_runtime(entry.id, entry.current_value, str(exc))
                continue
            values[entry.id] = text
            self._watches.update_runtime(entry.id, text, None)
            freeze_targets.append(FreezeTarget(entry, address, raw))
        freeze_result = self._freezer.apply(freeze_targets)
        for watch_id, value in freeze_result.written_values.items():
            values[watch_id] = value
            self._watches.update_runtime(watch_id, value, None)
        for watch_id, error in freeze_result.errors.items():
            current = values.get(watch_id, "")
            self._watches.update_runtime(watch_id, current, error)
        if freeze_result.limit_reached:
            self.write_error.emit(
                "Se alcanzó el límite de 32 escrituras de congelado por ciclo. "
                "Reduce las vigilancias congeladas o aumenta sus intervalos."
            )
        elif freeze_result.errors:
            self.write_error.emit(next(iter(freeze_result.errors.values())))
        if values:
            self.values.emit(values)
        if rows_due:
            self._emit_rows(raw_by_key)

    @Slot()
    def stop(self) -> None:
        """Stop the timer in its owning thread and finish the worker once."""
        if self._stopped:
            return
        self._stopped = True
        if self._timer is None:
            return
        self._timer.stop()
        self.finished.emit()

    def _emit_rows(self, raw_by_key: Mapping[tuple[str, str | int], bytes]) -> None:
        displayed: dict[int, str] = {}
        updates: dict[int, RowRefresh] = {}
        for address, data_type in self._visible.rows:
            raw = raw_by_key.get(("row", address))
            if raw is None:
                continue
            try:
                text = decode_value(data_type, raw)
            except Exception:
                continue
            old = self._row_previous.get(address)
            rate = 0.9 * self._row_rates.get(address, 0.0) + (0.1 if old != text else 0.0)
            self._row_previous[address] = text
            self._row_rates[address] = rate
            displayed[address] = text
            updates[address] = RowRefresh(data_type, raw, text, rate, self._visible.session_id)
        if displayed:
            self.row_values.emit(displayed)
            self.row_updates.emit(updates)

    def _read_grouped(self, targets: Sequence[_ReadTarget]) -> dict[tuple[str, str | int], bytes]:
        if not targets:
            return {}
        ordered = sorted(targets, key=lambda target: (target.address, target.size))
        groups: list[list[_ReadTarget]] = []
        current: list[_ReadTarget] = []
        group_base = 0
        group_end = 0
        for target in ordered:
            target_end = target.address + target.size
            if not current or target_end - group_base <= 4096:
                if not current:
                    group_base = target.address
                current.append(target)
                group_end = max(group_end, target_end)
            else:
                groups.append(current)
                current = [target]
                group_base = target.address
                group_end = target_end
        if current:
            groups.append(current)
        output: dict[tuple[str, str | int], bytes] = {}
        for group in groups:
            base = group[0].address
            end = max(target.address + target.size for target in group)
            buffer = bytearray(end - base)
            count = self._backend.read_into(base, memoryview(buffer))
            for target in group:
                relative = target.address - base
                if relative + target.size <= count:
                    output[target.key] = bytes(buffer[relative : relative + target.size])
                    continue
                fallback = bytearray(target.size)
                fallback_count = self._backend.read_into(target.address, memoryview(fallback))
                if fallback_count == target.size:
                    output[target.key] = bytes(fallback)
        return output

    @staticmethod
    def _watch_size(entry: WatchEntry) -> int:
        if entry.data_type in NUMERIC_TYPES:
            return type_size(entry.data_type)
        if entry.desired_value:
            return max(1, len(encode_value(entry.data_type, entry.desired_value)))
        return 256 if entry.data_type in {DataType.STRING_UTF8, DataType.STRING_UTF16} else 16

    @staticmethod
    def _row_size(data_type: DataType) -> int:
        if data_type in NUMERIC_TYPES:
            return type_size(data_type)
        return 256 if data_type in {DataType.STRING_UTF8, DataType.STRING_UTF16} else 16

    @staticmethod
    def _bounded_interval(interval_ms: int) -> int:
        return min(5000, max(50, interval_ms))


def start_worker(worker: _BaseWorker, on_finished: Callable[[], None]) -> QThread:
    """Start a parentless worker with the sole approved QObject/QThread lifecycle."""
    if worker.parent() is not None:
        raise ValueError("Un worker debe crearse sin padre antes de moverlo a un QThread.")
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(
        lambda: QMetaObject.invokeMethod(worker, "run", Qt.ConnectionType.QueuedConnection),
        Qt.ConnectionType.DirectConnection,
    )
    worker.finished.connect(on_finished)
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
