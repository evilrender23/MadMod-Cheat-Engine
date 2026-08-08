"""Exact-scan contracts over the in-memory backend."""

from __future__ import annotations

import threading

import pytest
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.data_types import DataType, encode_value
from mempilot.core.exceptions import ScanError
from mempilot.core.scanner import ScanEngine, ScanMode, ScanOptions, ScanRequest

IDENTITY = ProcessIdentity(4040, "target.exe", 1.0, None, Architecture.X64)


def scan(
    backend: FakeMemoryBackend,
    data_type: DataType,
    value: str,
    *,
    alignment: int = 0,
    chunk_size: int = 7,
    max_candidates: int = 100,
):
    request = ScanRequest(
        data_type,
        ScanMode.EXACT,
        value,
        None,
        ScanOptions(
            alignment=alignment,
            chunk_size=chunk_size,
            max_candidates=max_candidates,
        ),
    )
    return ScanEngine(backend).first_scan(request, threading.Event(), lambda _progress: None)


@pytest.mark.parametrize(
    ("data_type", "value", "offsets"),
    [
        (DataType.INT32, "-123456", [4, 20]),
        (DataType.UINT16, "65000", [2, 18]),
        (DataType.FLOAT32, "3.25", [8, 24]),
        (DataType.FLOAT64, "-8.5", [8, 32]),
        (DataType.BOOL, "sí", [3, 17]),
    ],
)
def test_exact_scan_finds_seeded_values(
    data_type: DataType, value: str, offsets: list[int]
) -> None:
    base = 0x1000
    memory = bytearray(64)
    encoded = encode_value(data_type, value)
    for offset in offsets:
        memory[offset : offset + len(encoded)] = encoded
    backend = FakeMemoryBackend([(base, memory, 0x04)], IDENTITY)

    result = scan(backend, data_type, value)

    assert result.addresses.tolist() == [base + offset for offset in offsets]


def test_alignment_one_finds_unaligned_value_and_chunk_overlap_does_not_duplicate() -> None:
    base = 0x2000
    memory = bytearray(24)
    memory[5:9] = encode_value(DataType.INT32, "987654321")
    backend = FakeMemoryBackend([(base, memory, 0x04)], IDENTITY)

    aligned = scan(backend, DataType.INT32, "987654321", alignment=0, chunk_size=7)
    unaligned = scan(backend, DataType.INT32, "987654321", alignment=1, chunk_size=7)

    assert aligned.addresses.size == 0
    assert unaligned.addresses.tolist() == [base + 5]


def test_candidate_limit_raises_instead_of_truncating() -> None:
    backend = FakeMemoryBackend([(0x3000, bytearray(64), 0x04)], IDENTITY)

    with pytest.raises(ScanError, match="Demasiados candidatos"):
        scan(backend, DataType.INT32, "0", max_candidates=2)
