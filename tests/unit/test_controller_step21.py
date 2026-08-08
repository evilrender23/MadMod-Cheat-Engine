"""Focused facade coverage for the Step 2.1 controller contract."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.config.settings import Settings, UISettings
from mempilot.controller import Actor, AppController
from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.data_types import DataType
from mempilot.core.exceptions import PolicyDenied
from mempilot.core.scan_session import FilterSpec, OrderSpec, SessionState
from mempilot.core.scanner import ScanMode, ScanOptions, ScanRequest
from mempilot.core.watcher import WatchSpec
from mempilot.services.audit_service import AuditService


@dataclass
class _PolicyBinding:
    bound_identity: ProcessIdentity | None = None


def _identity(create_time: float = 10.0) -> ProcessIdentity:
    return ProcessIdentity(4242, "target.exe", create_time, "C:/target.exe", Architecture.X64)


def _controller(tmp_path: Path) -> tuple[AppController, FakeMemoryBackend, _PolicyBinding]:
    identity = _identity()
    memory = bytearray(256)
    struct.pack_into("<i", memory, 32, 100)
    backend = FakeMemoryBackend([(0x1000, memory, 0x04)], identity)
    policy = _PolicyBinding()
    audit_path = tmp_path / "audit.jsonl"
    settings = Settings(ui=UISettings(watch_refresh_ms=50, results_refresh_ms=50))
    controller = AppController(
        backend,
        audit_service=AuditService(audit_path),
        settings=settings,
        agent_policy=policy,
    )
    controller.attach(identity.pid, True, Actor.USER)
    return controller, backend, policy


def test_controller_read_write_scan_and_page(qtbot: QtBot, tmp_path: Path) -> None:
    controller, backend, _policy = _controller(tmp_path)
    try:
        assert controller.read_address(0x1020, DataType.INT32) == "100"
        controller.write_address(0x1020, DataType.INT32, "125", Actor.USER)
        assert struct.unpack("<i", backend.read(0x1020, 4))[0] == 125
        backend.poke(0x1020, struct.pack("<i", 100))
        request = ScanRequest(
            DataType.INT32,
            ScanMode.EXACT,
            "100",
            None,
            ScanOptions(chunk_size=64),
        )
        with qtbot.waitSignal(controller.scan_finished, timeout=3000):  # type: ignore[attr-defined]
            session_id = controller.start_scan(request, Actor.USER)
        assert controller.scan_status().session_id == session_id
        assert controller.scan_status().state is SessionState.READY
        page = controller.results_page(0, 10, OrderSpec(), FilterSpec())
        assert [row.address for row in page.rows] == [0x1020]
        assert page.total == page.total_unfiltered == 1
    finally:
        controller.shutdown()


def test_agent_operations_require_bound_process_identity(tmp_path: Path) -> None:
    controller, backend, policy = _controller(tmp_path)
    try:
        policy.bound_identity = _identity(create_time=99.0)
        with pytest.raises(PolicyDenied):
            controller.write_address(0x1020, DataType.INT32, "200", Actor.AGENT)
        assert struct.unpack("<i", backend.read(0x1020, 4))[0] == 100
    finally:
        controller.shutdown()


def test_watch_freeze_runs_on_single_scheduler(qtbot: QtBot, tmp_path: Path) -> None:
    controller, backend, _policy = _controller(tmp_path)
    try:
        entry = controller.add_watch(
            WatchSpec("Vida", DataType.INT32, address=0x1020, interval_ms=50),
            Actor.USER,
        )
        controller.set_freeze(entry.id, True, "100", 50, Actor.USER)
        backend.poke(0x1020, struct.pack("<i", 73))
        qtbot.waitUntil(  # type: ignore[attr-defined]
            lambda: struct.unpack("<i", backend.read(0x1020, 4))[0] == 100,
            timeout=3000,
        )
        controller.set_freeze(entry.id, False, None, 50, Actor.USER)
        assert controller.list_watches()[0].frozen is False
    finally:
        controller.shutdown()
