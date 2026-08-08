"""End-to-end Win32 memory scan, write, and freeze roundtrip."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from mempilot.config.settings import Settings, UISettings
from mempilot.controller import Actor, AppController
from mempilot.core.data_types import DataType
from mempilot.core.scan_session import FilterSpec, OrderSpec
from mempilot.core.scanner import ScanMode, ScanOptions, ScanRequest
from mempilot.core.watcher import WatchSpec
from mempilot.core.win32_backend import Win32MemoryBackend
from mempilot.services.audit_service import AuditService
from tests.integration._target import TargetProcess

pytestmark = [pytest.mark.windows, pytest.mark.integration]


def _exact_request(value: int, target: TargetProcess) -> ScanRequest:
    return ScanRequest(
        data_type=DataType.INT32,
        mode=ScanMode.EXACT,
        value=str(value),
        value2=None,
        options=ScanOptions(
            alignment=1,
            writable_only=True,
            include_image=False,
            include_mapped=False,
            chunk_size=64 << 10,
            max_candidates=100_000,
            address_min=target.address("scan_min"),
            address_max=target.address("scan_max"),
        ),
    )


def _health(response: dict[str, Any]) -> int:
    value = response.get("health")
    if not isinstance(value, int):
        raise AssertionError(f"Target response has no integer health: {response!r}")
    return value


def test_real_process_scan_write_freeze_and_cleanup(tmp_path: Path, qtbot: QtBot) -> None:
    target = TargetProcess.start()
    baseline_threads = {thread.ident for thread in threading.enumerate()}
    backend = Win32MemoryBackend()
    controller = AppController(
        backend,
        audit_service=AuditService(tmp_path / "audit.jsonl"),
        settings=Settings(
            ui=UISettings(
                results_page_size=100,
                results_refresh_ms=50,
                watch_refresh_ms=50,
            )
        ),
    )
    health_address = target.address("health")

    try:
        identity = controller.attach(target.pid, True, Actor.USER)
        assert identity.pid == target.pid
        assert backend.is_open

        with qtbot.waitSignal(controller.scan_finished, timeout=15_000):  # type: ignore[attr-defined]
            controller.start_scan(_exact_request(100, target), Actor.USER)

        initial = controller.results_page(0, 100, OrderSpec(), FilterSpec())
        initial_addresses = {row.address for row in initial.rows}
        assert health_address in initial_addresses
        assert initial.total_unfiltered >= 1

        assert _health(target.command("damage")) == 73
        with qtbot.waitSignal(controller.scan_finished, timeout=10_000):  # type: ignore[attr-defined]
            controller.refine_scan(_exact_request(73, target), Actor.USER)

        refined = controller.results_page(0, 100, OrderSpec(), FilterSpec())
        refined_addresses = {row.address for row in refined.rows}
        assert health_address in refined_addresses
        assert 1 <= refined.total_unfiltered <= 8
        assert refined.total_unfiltered <= initial.total_unfiltered

        controller.write_address(health_address, DataType.INT32, "250", Actor.USER)
        assert _health(target.command("get health")) == 250

        watch = controller.add_watch(
            WatchSpec(
                label="health",
                data_type=DataType.INT32,
                address=health_address,
                interval_ms=50,
            ),
            Actor.USER,
        )
        controller.set_freeze(watch.id, True, "100", 50, Actor.USER)
        target.command("damage")

        def frozen_value_restored() -> bool:
            return _health(target.command("get health")) == 100

        qtbot.waitUntil(frozen_value_restored, timeout=5_000)

        controller.set_freeze(watch.id, False, None, 50, Actor.USER)
        assert _health(target.command("damage")) == 73
        qtbot.wait(200)
        assert _health(target.command("get health")) == 73

        controller.shutdown()
        qtbot.waitUntil(
            lambda: all(
                thread is None or not thread.isRunning()
                for thread in (
                    controller._scan_thread,
                    controller._scheduler_thread,
                    controller._agent_thread,
                )
            ),
            timeout=5_000,
        )
        assert not backend.is_open
        assert {thread.ident for thread in threading.enumerate()} <= baseline_threads
    finally:
        controller.shutdown()
        target.close()
