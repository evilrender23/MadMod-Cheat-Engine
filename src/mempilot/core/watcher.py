"""Thread-safe watch definitions and address resolution."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from uuid import uuid4

from mempilot.core.backend import MemoryBackend, ModuleInfo
from mempilot.core.data_types import DataType
from mempilot.core.exceptions import InvalidAddressError, WorkspaceError
from mempilot.core.pointer_chain import PointerChain, resolve_chain


@dataclass(frozen=True, slots=True)
class WatchSpec:
    """Input accepted when adding a memory watch."""

    label: str
    data_type: DataType
    address: int | None = None
    module: str | None = None
    offset: int | None = None
    chain: PointerChain | None = None
    interval_ms: int = 100
    notes: str = ""

    def __post_init__(self) -> None:
        modes = sum(
            (
                self.address is not None,
                self.module is not None or self.offset is not None,
                self.chain is not None,
            )
        )
        if modes != 1:
            raise InvalidAddressError(
                "La vigilancia debe usar una dirección absoluta, "
                "módulo+offset o cadena de punteros."
            )
        if self.address is not None and self.address < 0:
            raise InvalidAddressError("La dirección de vigilancia no puede ser negativa.")
        if (self.module is None) != (self.offset is None):
            raise InvalidAddressError("El módulo y el offset deben indicarse juntos.")
        if self.module is not None and not self.module.strip():
            raise InvalidAddressError("El nombre del módulo no puede estar vacío.")
        if not 50 <= self.interval_ms <= 5000:
            raise ValueError("El intervalo de vigilancia debe estar entre 50 y 5000 ms.")


@dataclass(slots=True)
class WatchEntry:
    """Persisted watch definition plus its mutable runtime state."""

    id: str
    label: str
    data_type: DataType
    address: int | None = None
    module: str | None = None
    offset: int | None = None
    chain: PointerChain | None = None
    interval_ms: int = 100
    notes: str = ""
    frozen: bool = False
    desired_value: str | None = None
    current_value: str = ""
    last_error: str | None = None

    @classmethod
    def from_spec(cls, spec: WatchSpec, *, watch_id: str | None = None) -> WatchEntry:
        """Create a runtime entry while preserving the requested addressing mode."""
        return cls(
            id=watch_id or uuid4().hex[:12],
            label=spec.label,
            data_type=spec.data_type,
            address=spec.address,
            module=spec.module,
            offset=spec.offset,
            chain=spec.chain,
            interval_ms=spec.interval_ms,
            notes=spec.notes,
        )

    @property
    def address_mode(self) -> str:
        """Return the workspace addressing discriminator."""
        if self.address is not None:
            return "absolute"
        if self.chain is not None:
            return "pointer_chain"
        return "module_offset"


class WatchTable:
    """Lock-protected watch collection shared by the GUI and scheduler threads."""

    def __init__(self, on_changed: Callable[[], None] | None = None) -> None:
        self._entries: dict[str, WatchEntry] = {}
        self._lock = threading.RLock()
        self._on_changed = on_changed

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def add(self, spec: WatchSpec, *, watch_id: str | None = None) -> WatchEntry:
        """Add a watch and return a detached snapshot of it."""
        entry = WatchEntry.from_spec(spec, watch_id=watch_id)
        with self._lock:
            if entry.id in self._entries:
                raise ValueError(f"Ya existe una vigilancia con id {entry.id}.")
            self._entries[entry.id] = entry
        self._emit_changed()
        return replace(entry)

    def remove(self, watch_id: str) -> WatchEntry:
        """Remove a watch or raise a user-actionable key error."""
        with self._lock:
            try:
                entry = self._entries.pop(watch_id)
            except KeyError:
                raise KeyError(f"No existe la vigilancia {watch_id}.") from None
        self._emit_changed()
        return replace(entry)

    def get(self, watch_id: str) -> WatchEntry:
        """Return a detached snapshot safe to use outside the table lock."""
        with self._lock:
            try:
                return replace(self._entries[watch_id])
            except KeyError:
                raise KeyError(f"No existe la vigilancia {watch_id}.") from None

    def entries(self) -> list[WatchEntry]:
        """Return stable snapshots in insertion order."""
        with self._lock:
            return [replace(entry) for entry in self._entries.values()]

    def update(
        self,
        watch_id: str,
        *,
        label: str | None = None,
        desired_value: str | None = None,
        interval_ms: int | None = None,
        notes: str | None = None,
    ) -> WatchEntry:
        """Update user-editable metadata and return a detached snapshot."""
        if interval_ms is not None and not 50 <= interval_ms <= 5000:
            raise ValueError("El intervalo de vigilancia debe estar entre 50 y 5000 ms.")
        if label is not None and not label.strip():
            raise ValueError("El nombre de la vigilancia no puede estar vacío.")
        with self._lock:
            entry = self._entry(watch_id)
            if label is not None:
                entry.label = label.strip()
            if desired_value is not None:
                entry.desired_value = desired_value
            if interval_ms is not None:
                entry.interval_ms = interval_ms
            if notes is not None:
                entry.notes = notes
            snapshot = replace(entry)
        self._emit_changed()
        return snapshot

    def set_written_value(self, watch_id: str, value: str) -> WatchEntry:
        """Update the desired and observed value after an explicit write."""
        with self._lock:
            entry = self._entry(watch_id)
            entry.desired_value = value
            entry.current_value = value
            entry.last_error = None
            snapshot = replace(entry)
        self._emit_changed()
        return snapshot

    def set_freeze(
        self,
        watch_id: str,
        *,
        frozen: bool,
        desired_value: str | None,
        interval_ms: int,
    ) -> WatchEntry:
        """Update freeze state after the controller has validated the value."""
        if not 50 <= interval_ms <= 5000:
            raise ValueError("El intervalo de congelado debe estar entre 50 y 5000 ms.")
        with self._lock:
            entry = self._entry(watch_id)
            next_desired = desired_value if desired_value is not None else entry.desired_value
            if frozen and next_desired is None:
                raise ValueError("Indica un valor deseado antes de congelar la vigilancia.")
            entry.frozen = frozen
            entry.interval_ms = interval_ms
            entry.desired_value = next_desired
            snapshot = replace(entry)
        self._emit_changed()
        return snapshot

    def update_runtime(self, watch_id: str, current_value: str, error: str | None) -> None:
        """Store scheduler output without emitting a structural-change notification."""
        with self._lock:
            entry = self._entries.get(watch_id)
            if entry is None:
                return
            entry.current_value = current_value
            entry.last_error = error

    def replace_all(self, entries: Sequence[WatchEntry]) -> None:
        """Atomically replace the collection, rejecting duplicate identifiers."""
        replacement = {entry.id: replace(entry) for entry in entries}
        if len(replacement) != len(entries):
            raise WorkspaceError("El workspace contiene identificadores de vigilancia duplicados.")
        with self._lock:
            self._entries = replacement
        self._emit_changed()

    def to_models(self) -> list[object]:
        """Convert watches to workspace models without runtime-only fields."""
        from mempilot.services.workspace_service import WatchEntryModel

        models: list[object] = []
        for entry in self.entries():
            models.append(
                WatchEntryModel(
                    id=entry.id,
                    label=entry.label,
                    address_mode=entry.address_mode,
                    address=entry.address,
                    module=entry.module,
                    offset=entry.offset,
                    chain_id=entry.chain.id if entry.chain is not None else None,
                    data_type=entry.data_type,
                    desired_value=entry.desired_value,
                    frozen=entry.frozen,
                    interval_ms=entry.interval_ms,
                    notes=entry.notes,
                )
            )
        return models

    @classmethod
    def from_models(
        cls,
        models: Sequence[object],
        pointer_chains: Sequence[PointerChain] = (),
        *,
        on_changed: Callable[[], None] | None = None,
    ) -> WatchTable:
        """Restore workspace models and reconnect pointer-chain references."""
        from mempilot.services.workspace_service import WatchEntryModel

        chains = {chain.id: chain for chain in pointer_chains}
        entries: list[WatchEntry] = []
        for raw_model in models:
            if not isinstance(raw_model, WatchEntryModel):
                raise TypeError("Se esperaba un modelo de vigilancia de workspace.")
            model = raw_model
            chain = None
            if model.address_mode == "pointer_chain":
                if model.chain_id is None or model.chain_id not in chains:
                    raise WorkspaceError(
                        f"La vigilancia {model.label!r} referencia una cadena de punteros ausente."
                    )
                chain = chains[model.chain_id]
            spec = WatchSpec(
                label=model.label,
                data_type=model.data_type,
                address=model.address if model.address_mode == "absolute" else None,
                module=model.module if model.address_mode == "module_offset" else None,
                offset=model.offset if model.address_mode == "module_offset" else None,
                chain=chain,
                interval_ms=model.interval_ms,
                notes=model.notes,
            )
            entry = WatchEntry.from_spec(spec, watch_id=model.id)
            entry.desired_value = model.desired_value
            entry.frozen = model.frozen
            entries.append(entry)
        table = cls(on_changed)
        table.replace_all(entries)
        return table

    def _entry(self, watch_id: str) -> WatchEntry:
        try:
            return self._entries[watch_id]
        except KeyError:
            raise KeyError(f"No existe la vigilancia {watch_id}.") from None

    def _emit_changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()


def resolve_watch_address(
    entry: WatchEntry,
    backend: MemoryBackend,
    modules: Sequence[ModuleInfo],
) -> tuple[int | None, str | None]:
    """Resolve any watch addressing mode without leaking backend exceptions."""
    if entry.address is not None:
        return entry.address, None
    if entry.module is not None and entry.offset is not None:
        module = next(
            (
                candidate
                for candidate in modules
                if candidate.name.casefold() == entry.module.casefold()
            ),
            None,
        )
        if module is None:
            return None, f"El módulo {entry.module!r} no está cargado."
        address = module.base + entry.offset
        if address < 0:
            return None, "El offset produce una dirección negativa."
        return address, None
    if entry.chain is not None:
        resolution = resolve_chain(entry.chain, backend, modules)
        return resolution.final_address, resolution.error
    return None, "La vigilancia no tiene un modo de dirección válido."
