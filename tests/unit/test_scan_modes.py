"""Numeric refinement modes and unknown-initial snapshots."""

from __future__ import annotations

import threading

import numpy as np
import pytest
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.data_types import DataType, encode_value, numpy_dtype
from mempilot.core.scanner import (
    CandidateSet,
    ScanEngine,
    ScanMode,
    ScanOptions,
    ScanRequest,
    UnknownSnapshot,
)

IDENTITY = ProcessIdentity(5050, "values.exe", 2.0, None, Architecture.X64)
BASE = 0x4000
OLD = [10, 20, 30, 40]
CURRENT = [10, 25, 20, 45]


def make_backend() -> FakeMemoryBackend:
    memory = bytearray(64)
    for index, value in enumerate(CURRENT):
        memory[index * 4 : index * 4 + 4] = encode_value(DataType.INT32, str(value))
    return FakeMemoryBackend([(BASE, memory, 0x04)], IDENTITY)


@pytest.mark.parametrize(
    ("mode", "value", "value2", "expected"),
    [
        (ScanMode.CHANGED, None, None, [1, 2, 3]),
        (ScanMode.UNCHANGED, None, None, [0]),
        (ScanMode.INCREASED, None, None, [1, 3]),
        (ScanMode.DECREASED, None, None, [2]),
        (ScanMode.INCREASED_BY, "5", None, [1, 3]),
        (ScanMode.DECREASED_BY, "10", None, [2]),
        (ScanMode.BETWEEN, "20", "30", [1, 2]),
        (ScanMode.GREATER_THAN, "25", None, [3]),
        (ScanMode.LESS_THAN, "20", None, [0]),
        (ScanMode.EXACT, "25", None, [1]),
    ],
)
def test_refine_modes(
    mode: ScanMode,
    value: str | None,
    value2: str | None,
    expected: list[int],
) -> None:
    backend = make_backend()
    previous = CandidateSet(
        addresses=np.asarray([BASE + index * 4 for index in range(4)], dtype=np.uint64),
        values=np.asarray(OLD, dtype=numpy_dtype(DataType.INT32)),
        data_type=DataType.INT32,
    )
    request = ScanRequest(DataType.INT32, mode, value, value2, ScanOptions())

    result = ScanEngine(backend).refine(
        previous, request, threading.Event(), lambda _progress: None
    )

    assert result.addresses.tolist() == [BASE + index * 4 for index in expected]
    assert backend.read_into_calls == 1


def test_unknown_snapshot_respects_budget_and_refines_changed_values() -> None:
    first = bytearray(1 << 20)
    second = bytearray(1 << 20)
    first[12:16] = encode_value(DataType.INT32, "100")
    backend = FakeMemoryBackend([(BASE, first, 0x04), (BASE + (2 << 20), second, 0x04)], IDENTITY)
    initial = ScanRequest(
        DataType.INT32,
        ScanMode.UNKNOWN_INITIAL,
        None,
        None,
        ScanOptions(unknown_budget_mb=1, chunk_size=128 << 10),
    )
    engine = ScanEngine(backend)

    snapshot = engine.first_scan(initial, threading.Event(), lambda _progress: None)
    assert isinstance(snapshot, UnknownSnapshot)
    assert snapshot.regions_skipped == 1
    backend.poke(BASE + 12, encode_value(DataType.INT32, "73"))
    changed = ScanRequest(DataType.INT32, ScanMode.CHANGED, None, None, initial.options)

    result = engine.refine(snapshot, changed, threading.Event(), lambda _progress: None)

    assert result.addresses.tolist() == [BASE + 12]
    assert result.values.tolist() == [73]
