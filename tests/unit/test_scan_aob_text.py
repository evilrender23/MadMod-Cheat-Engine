"""AOB and text scanning across chunk boundaries."""

from __future__ import annotations

import threading

import pytest
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.data_types import DataType
from mempilot.core.exceptions import ScanCancelled
from mempilot.core.scanner import ScanEngine, ScanMode, ScanOptions, ScanRequest

IDENTITY = ProcessIdentity(6060, "strings.exe", 3.0, None, Architecture.X64)
BASE = 0x8000


def run_scan(
    backend: FakeMemoryBackend,
    data_type: DataType,
    mode: ScanMode,
    value: str,
    *,
    case_sensitive: bool = True,
):
    request = ScanRequest(
        data_type,
        mode,
        value,
        None,
        ScanOptions(chunk_size=8, case_sensitive=case_sensitive),
    )
    return ScanEngine(backend).first_scan(request, threading.Event(), lambda _progress: None)


def test_aob_wildcards_find_pattern_crossing_chunk_boundary_once() -> None:
    memory = bytearray(40)
    marker = bytes.fromhex("4D 45 4D 50 DE AD BE EF 11 22 33 44 55 66 77 88")
    memory[6 : 6 + len(marker)] = marker
    backend = FakeMemoryBackend([(BASE, memory, 0x04)], IDENTITY)

    result = run_scan(
        backend,
        DataType.AOB,
        ScanMode.AOB,
        "4D 45 4D 50 ?? ?? BE EF 11 22 33 44 55 66 77 88",
    )

    assert result.addresses.tolist() == [BASE + 6]
    assert result.values == [marker]


@pytest.mark.parametrize(
    ("data_type", "stored", "query"),
    [
        (DataType.STRING_UTF8, b"PlayerOne", "playerone"),
        (DataType.STRING_UTF16, "PlayerOne".encode("utf-16-le"), "playerone"),
    ],
)
def test_text_case_sensitivity(data_type: DataType, stored: bytes, query: str) -> None:
    memory = bytearray(48)
    memory[7 : 7 + len(stored)] = stored
    backend = FakeMemoryBackend([(BASE, memory, 0x04)], IDENTITY)

    sensitive = run_scan(backend, data_type, ScanMode.TEXT, query)
    insensitive = run_scan(backend, data_type, ScanMode.TEXT, query, case_sensitive=False)
    exact_case = run_scan(backend, data_type, ScanMode.TEXT, "PlayerOne")

    assert sensitive.addresses.size == 0
    assert insensitive.addresses.tolist() == [BASE + 7]
    assert exact_case.addresses.tolist() == [BASE + 7]


def test_cancel_is_checked_before_each_chunk() -> None:
    backend = FakeMemoryBackend([(BASE, bytearray(128), 0x04)], IDENTITY)
    request = ScanRequest(
        DataType.INT32,
        ScanMode.EXACT,
        "0",
        None,
        ScanOptions(chunk_size=8),
    )
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(ScanCancelled):
        ScanEngine(backend).first_scan(request, cancel, lambda _progress: None)
