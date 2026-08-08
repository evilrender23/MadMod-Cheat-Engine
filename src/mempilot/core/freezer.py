"""Pure freeze decisions and bounded write execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from mempilot.core.backend import MemoryBackend
from mempilot.core.data_types import encode_value
from mempilot.core.watcher import WatchEntry

MAX_FREEZE_WRITES_PER_TICK = 32


class FreezeAuditSink(Protocol):
    """Minimal audit contract consumed by the freeze loop."""

    def record_freeze_writes(
        self,
        count: int,
        *,
        actor: str = "system",
        target: str = "vigilancias",
        detail: str = "",
    ) -> object | None: ...


@dataclass(frozen=True, slots=True)
class FreezeTarget:
    """One resolved watch and the bytes observed during the scheduler read."""

    entry: WatchEntry
    address: int
    current: bytes


@dataclass(slots=True)
class FreezeTickResult:
    """Observable outcome of one bounded freezer pass."""

    writes: int = 0
    limit_reached: bool = False
    written_values: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class FreezeController:
    """Compare frozen values and write only when their bytes differ."""

    def __init__(
        self,
        backend: MemoryBackend,
        audit: FreezeAuditSink,
        *,
        max_writes_per_tick: int = MAX_FREEZE_WRITES_PER_TICK,
    ) -> None:
        if max_writes_per_tick < 1:
            raise ValueError("El límite de escrituras por tick debe ser positivo.")
        self._backend = backend
        self._audit = audit
        self._max_writes = max_writes_per_tick
        self._encoded_cache: dict[tuple[object, str], bytes] = {}

    @property
    def max_writes_per_tick(self) -> int:
        """Return the hard per-tick write ceiling."""
        return self._max_writes

    def desired_bytes(self, entry: WatchEntry) -> bytes:
        """Encode and cache a watch's desired value."""
        if entry.desired_value is None:
            raise ValueError("La vigilancia congelada no tiene un valor deseado.")
        key = (entry.data_type, entry.desired_value)
        encoded = self._encoded_cache.get(key)
        if encoded is None:
            encoded = encode_value(entry.data_type, entry.desired_value)
            self._encoded_cache[key] = encoded
        return encoded

    def should_write(self, entry: WatchEntry, current: bytes) -> bool:
        """Return whether a frozen entry differs byte-for-byte from its desired value."""
        return entry.frozen and current != self.desired_bytes(entry)

    def apply(self, targets: Sequence[FreezeTarget]) -> FreezeTickResult:
        """Apply at most 32 differing writes and aggregate their audit heartbeat."""
        result = FreezeTickResult()
        for target in targets:
            entry = target.entry
            if not entry.frozen:
                continue
            try:
                desired = self.desired_bytes(entry)
            except (TypeError, ValueError) as exc:
                result.errors[entry.id] = str(exc)
                continue
            if target.current == desired:
                continue
            if result.writes >= self._max_writes:
                result.limit_reached = True
                continue
            try:
                written = self._backend.write(target.address, desired)
                if written != len(desired):
                    raise OSError(
                        f"Escritura parcial: {written} de {len(desired)} bytes "
                        f"en 0x{target.address:016X}."
                    )
            except Exception as exc:
                result.errors[entry.id] = str(exc)
                continue
            result.writes += 1
            assert entry.desired_value is not None
            result.written_values[entry.id] = entry.desired_value
        self._audit.record_freeze_writes(
            result.writes,
            actor="system",
            target="vigilancias",
            detail="planificador de vigilancia",
        )
        return result

    def invalidate_cache(self) -> None:
        """Drop encoded values after a workspace or watch-set replacement."""
        self._encoded_cache.clear()


def differing_frozen_values(
    entries: Sequence[WatchEntry],
    current_by_id: Mapping[str, bytes],
) -> list[str]:
    """Return differing frozen ids as a backend-free unit-testable decision helper."""
    differing: list[str] = []
    for entry in entries:
        if not entry.frozen or entry.desired_value is None:
            continue
        current = current_by_id.get(entry.id)
        if current is None or current != encode_value(entry.data_type, entry.desired_value):
            differing.append(entry.id)
    return differing
