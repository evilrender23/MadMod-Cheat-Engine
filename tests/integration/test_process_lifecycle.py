"""Process-loss and controller shutdown integration contracts."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from mempilot.config.settings import Settings, UISettings
from mempilot.controller import Actor, AppController
from mempilot.core.data_types import DataType
from mempilot.core.exceptions import ProcessExitedError
from mempilot.core.scanner import ScanMode, ScanOptions, ScanRequest
from mempilot.core.win32_backend import Win32MemoryBackend
from mempilot.services.audit_service import AuditService
from tests.integration._target import TargetProcess

pytestmark = [pytest.mark.windows, pytest.mark.integration]


def test_process_exit_during_scan_detaches_and_shutdown_leaves_no_threads(
    tmp_path: Path, qtbot: QtBot
) -> None:
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

    try:
        controller.attach(target.pid, True, Actor.USER)
        request = ScanRequest(
            data_type=DataType.INT32,
            mode=ScanMode.EXACT,
            value="2139062143",
            value2=None,
            options=ScanOptions(
                alignment=1,
                writable_only=True,
                include_image=False,
                include_mapped=False,
                chunk_size=4096,
                max_candidates=1000,
                address_min=target.address("slow_min"),
                address_max=target.address("slow_max"),
            ),
        )

        with qtbot.waitSignal(controller.scan_started, timeout=5_000):  # type: ignore[attr-defined]
            controller.start_scan(request, Actor.USER)
        assert controller._scan_thread is not None
        assert controller._scan_thread.isRunning()

        target.kill()
        with (
            qtbot.waitSignal(controller.detached, timeout=10_000),  # type: ignore[attr-defined]
            pytest.raises(ProcessExitedError),
        ):
            controller.read_address(target.address("health"), DataType.INT32)

        assert controller.attached_identity() is None
        assert not backend.is_open
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
        assert {thread.ident for thread in threading.enumerate()} <= baseline_threads
    finally:
        controller.shutdown()
        target.close()
