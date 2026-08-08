"""Pure watch collection and bounded freezer behavior."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.core.backend import Architecture, ModuleInfo, ProcessIdentity
from mempilot.core.data_types import DataType, encode_value
from mempilot.core.exceptions import InvalidAddressError
from mempilot.core.freezer import FreezeController, FreezeTarget, differing_frozen_values
from mempilot.core.watcher import WatchEntry, WatchSpec, WatchTable, resolve_watch_address

IDENTITY = ProcessIdentity(9191, "watch.exe", 7.0, None, Architecture.X64)
BASE = 0xC000


@dataclass
class _AuditSink:
    calls: list[tuple[int, str, str, str]] = field(default_factory=list)

    def record_freeze_writes(
        self,
        count: int,
        *,
        actor: str = "system",
        target: str = "vigilancias",
        detail: str = "",
    ) -> None:
        self.calls.append((count, actor, target, detail))


class _PartialWriteBackend(FakeMemoryBackend):
    def write(self, address: int, data: bytes) -> int:
        return max(0, len(data) - 1)


def _entry(
    watch_id: str,
    offset: int,
    *,
    desired: str | None,
    frozen: bool,
) -> WatchEntry:
    return WatchEntry(
        id=watch_id,
        label=watch_id,
        data_type=DataType.INT32,
        address=BASE + offset,
        frozen=frozen,
        desired_value=desired,
    )


def test_freezer_writes_only_differing_values_and_enforces_tick_limit() -> None:
    memory = bytearray(16)
    memory[0:4] = encode_value(DataType.INT32, "73")
    memory[4:8] = encode_value(DataType.INT32, "100")
    memory[8:12] = encode_value(DataType.INT32, "50")
    backend = FakeMemoryBackend([(BASE, memory, 0x04)], IDENTITY)
    audit = _AuditSink()
    assert FreezeController(backend, audit).max_writes_per_tick == 32
    freezer = FreezeController(backend, audit, max_writes_per_tick=1)
    first = _entry("first", 0, desired="100", frozen=True)
    same = _entry("same", 4, desired="100", frozen=True)
    limited = _entry("limited", 8, desired="100", frozen=True)
    inactive = _entry("inactive", 12, desired=None, frozen=False)

    result = freezer.apply(
        [
            FreezeTarget(first, BASE, memory[0:4]),
            FreezeTarget(same, BASE + 4, memory[4:8]),
            FreezeTarget(limited, BASE + 8, memory[8:12]),
            FreezeTarget(inactive, BASE + 12, memory[12:16]),
        ]
    )

    assert result.writes == 1
    assert result.limit_reached is True
    assert result.written_values == {"first": "100"}
    assert result.errors == {}
    assert backend.read(BASE, 4) == encode_value(DataType.INT32, "100")
    assert backend.read(BASE + 8, 4) == encode_value(DataType.INT32, "50")
    assert audit.calls == [(1, "system", "vigilancias", "planificador de vigilancia")]


def test_freezer_reports_encoding_partial_write_and_closed_backend_errors() -> None:
    memory = bytearray(8)
    backend = _PartialWriteBackend([(BASE, memory, 0x04)], IDENTITY)
    audit = _AuditSink()
    freezer = FreezeController(backend, audit)
    invalid = _entry("invalid", 0, desired="not-an-int", frozen=True)
    partial = _entry("partial", 4, desired="100", frozen=True)

    result = freezer.apply(
        [
            FreezeTarget(invalid, BASE, memory[0:4]),
            FreezeTarget(partial, BASE + 4, memory[4:8]),
        ]
    )

    assert result.writes == 0
    assert set(result.errors) == {"invalid", "partial"}
    assert "Escritura parcial" in result.errors["partial"]
    assert audit.calls[-1][0] == 0

    closed_backend = FakeMemoryBackend([(BASE, bytearray(4), 0x04)], IDENTITY)
    closed_freezer = FreezeController(closed_backend, audit)
    closed_backend.close()
    after_shutdown = closed_freezer.apply(
        [FreezeTarget(_entry("closed", 0, desired="100", frozen=True), BASE, b"\x00" * 4)]
    )

    assert after_shutdown.writes == 0
    assert "closed" in after_shutdown.errors


def test_differing_frozen_values_ignores_inactive_and_detects_missing_reads() -> None:
    entries = [
        _entry("same", 0, desired="100", frozen=True),
        _entry("changed", 4, desired="100", frozen=True),
        _entry("missing", 8, desired="100", frozen=True),
        _entry("inactive", 12, desired="100", frozen=False),
        _entry("unset", 16, desired=None, frozen=True),
    ]

    differing = differing_frozen_values(
        entries,
        {
            "same": encode_value(DataType.INT32, "100"),
            "changed": encode_value(DataType.INT32, "73"),
            "inactive": encode_value(DataType.INT32, "73"),
        },
    )

    assert differing == ["changed", "missing"]


def test_watch_table_updates_atomically_and_returns_detached_snapshots() -> None:
    changes: list[str] = []
    table = WatchTable(lambda: changes.append("changed"))
    added = table.add(
        WatchSpec("Vida", DataType.INT32, address=BASE, interval_ms=100),
        watch_id="life",
    )
    added.label = "mutated snapshot"

    assert table.get("life").label == "Vida"
    with pytest.raises(ValueError, match="valor deseado"):
        table.set_freeze("life", frozen=True, desired_value=None, interval_ms=50)
    unchanged = table.get("life")
    assert unchanged.frozen is False
    assert unchanged.interval_ms == 100

    frozen = table.set_freeze("life", frozen=True, desired_value="100", interval_ms=50)
    table.update_runtime("life", "73", "lectura temporal")

    assert frozen.frozen is True
    assert frozen.desired_value == "100"
    assert table.get("life").current_value == "73"
    assert changes == ["changed", "changed"]

    removed = table.remove("life")
    assert removed.id == "life"
    assert len(table) == 0
    assert changes == ["changed", "changed", "changed"]


def test_watch_address_modes_validate_and_resolve_without_raising() -> None:
    backend = FakeMemoryBackend([(BASE, bytearray(32), 0x04)], IDENTITY)
    module = ModuleInfo("watch.exe", "C:/watch.exe", BASE, 32)
    absolute = WatchEntry.from_spec(WatchSpec("Abs", DataType.INT32, address=BASE + 4))
    relative = WatchEntry.from_spec(WatchSpec("Rel", DataType.INT32, module="WATCH.EXE", offset=8))

    assert resolve_watch_address(absolute, backend, [module]) == (BASE + 4, None)
    assert resolve_watch_address(relative, backend, [module]) == (BASE + 8, None)
    missing_address, missing_error = resolve_watch_address(relative, backend, [])
    assert missing_address is None
    assert missing_error == "El módulo 'WATCH.EXE' no está cargado."

    with pytest.raises(InvalidAddressError):
        WatchSpec("Ambigua", DataType.INT32, address=BASE, module="watch.exe", offset=0)
    with pytest.raises(InvalidAddressError):
        WatchSpec("Sin dirección", DataType.INT32)
