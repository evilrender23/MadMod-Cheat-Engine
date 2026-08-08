"""Pagination, filtering, history, and refresh behavior of scan sessions."""

from __future__ import annotations

import numpy as np
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.core.backend import Architecture, MemoryRegion, ProcessIdentity
from mempilot.core.data_types import DataType, encode_value, numpy_dtype
from mempilot.core.scan_session import FilterSpec, OrderSpec, ScanSession, SessionState
from mempilot.core.scanner import CandidateSet, ScanMode, ScanOptions, ScanRequest

IDENTITY = ProcessIdentity(7070, "page.exe", 4.0, None, Architecture.X64)
BASE = 0xA000


def make_session() -> ScanSession:
    session = ScanSession(IDENTITY, DataType.INT32, ScanOptions())
    result = CandidateSet(
        addresses=np.asarray([BASE + 12, BASE + 4, BASE + 8], dtype=np.uint64),
        values=np.asarray([30, 10, 20], dtype=numpy_dtype(DataType.INT32)),
        data_type=DataType.INT32,
    )
    request = ScanRequest(DataType.INT32, ScanMode.EXACT, "10", None, session.options)
    session.set_first_result(
        result,
        request,
        regions_scanned=1,
        bytes_scanned=64,
        duration_s=0.25,
        memory_regions=[MemoryRegion(BASE, 64, 0x04, 0x1000, 0x20000, "page.exe")],
    )
    return session


def test_page_applies_order_offset_limit_and_text_filter() -> None:
    session = make_session()

    page = session.page(1, 1, OrderSpec("value", descending=False), FilterSpec())
    filtered = session.page(0, 10, OrderSpec(), FilterSpec(text="20"))
    ranged = session.page(
        0,
        10,
        OrderSpec(descending=True),
        FilterSpec(address_min=BASE + 8, address_max=BASE + 12),
    )

    assert [(row.address, row.current) for row in page] == [(BASE + 8, "20")]
    assert [row.address for row in filtered] == [BASE + 8]
    assert [row.address for row in ranged] == [BASE + 12, BASE + 8]
    assert filtered[0].region == "page.exe+0x8"
    assert filtered[0].writable is True


def test_refinement_records_history_and_previous_values() -> None:
    session = make_session()
    refined = CandidateSet(
        addresses=np.asarray([BASE + 8], dtype=np.uint64),
        values=np.asarray([25], dtype=numpy_dtype(DataType.INT32)),
        data_type=DataType.INT32,
    )
    request = ScanRequest(DataType.INT32, ScanMode.INCREASED, None, None, session.options)

    session.set_refined_result(refined, request, duration_s=0.1)
    row = session.page(0, 1, OrderSpec(), FilterSpec())[0]

    assert session.state is SessionState.READY
    assert session.total() == 1
    assert row.current == "25"
    assert row.previous == "20"
    assert session.history[0].candidates_before == 3
    assert session.history[0].candidates_after == 1


def test_refresh_values_updates_materialized_value_and_change_rate() -> None:
    session = make_session()
    memory = bytearray(64)
    memory[8:12] = encode_value(DataType.INT32, "99")
    backend = FakeMemoryBackend([(BASE, memory, 0x04)], IDENTITY)

    values = session.refresh_values(backend, [BASE + 8, BASE + 99])
    row = session.page(0, 10, OrderSpec(), FilterSpec(text="99"))[0]

    assert values == {BASE + 8: "99"}
    assert row.current == "99"
    assert row.change_rate == 0.1
