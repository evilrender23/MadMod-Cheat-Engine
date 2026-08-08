"""Focused Win32 backend and process-policy contract tests."""

from __future__ import annotations

import ctypes
import os
import struct
import sys

import psutil
import pytest

if sys.platform != "win32":
    pytest.skip("Requiere Windows: las APIs Win32 no existen", allow_module_level=True)
import mempilot.core.win32_backend as win32_backend
from mempilot.core.backend import AccessMode, Architecture, ProcessIdentity
from mempilot.core.exceptions import (
    AccessDeniedError,
    InvalidAddressError,
    ProcessNotAllowedError,
    WriteNotPermittedError,
)
from mempilot.core.process_service import ProcessService
from mempilot.core.win32_api import (
    ERROR_ACCESS_DENIED,
    MEMORY_BASIC_INFORMATION64,
    PROCESS_QUERY_INFORMATION,
    PROCESS_VM_OPERATION,
    PROCESS_VM_READ,
    PROCESS_VM_WRITE,
)
from mempilot.core.win32_backend import Win32MemoryBackend

pytestmark = pytest.mark.windows


def current_identity() -> ProcessIdentity:
    """Return an identity suitable for opening this test process directly."""
    process = psutil.Process()
    return ProcessIdentity(
        pid=os.getpid(),
        name=process.name(),
        create_time=float(process.create_time()),
        path=process.exe(),
        architecture=Architecture.UNKNOWN,
    )


def test_memory_basic_information_x64_layout_is_48_bytes() -> None:
    assert ctypes.sizeof(MEMORY_BASIC_INFORMATION64) == 48


@pytest.mark.parametrize(
    ("mode", "expected_access"),
    [
        (AccessMode.READ, PROCESS_QUERY_INFORMATION | PROCESS_VM_READ),
        (
            AccessMode.READ_WRITE,
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION,
        ),
    ],
)
def test_open_uses_exact_access_mask_and_close_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    mode: AccessMode,
    expected_access: int,
) -> None:
    class FakeKernel32:
        def __init__(self) -> None:
            self.access = 0
            self.close_calls = 0

        def OpenProcess(self, access: int, inherit: bool, pid: int) -> int:
            self.access = access
            assert not inherit
            assert pid == 12345
            return 99

        def CloseHandle(self, handle: int) -> bool:
            assert handle == 99
            self.close_calls += 1
            return True

    fake = FakeKernel32()
    monkeypatch.setattr(win32_backend, "kernel32", fake)
    monkeypatch.setattr(
        win32_backend,
        "architecture_from_handle",
        lambda _handle: Architecture.X64,
    )
    identity = ProcessIdentity(12345, "target.exe", 1.0, None, Architecture.UNKNOWN)
    backend = Win32MemoryBackend()
    backend.open(identity, mode)
    backend.close()
    backend.close()

    assert fake.access == expected_access
    assert fake.close_calls == 1
    assert backend.identity is None


def test_access_denied_maps_to_actionable_contract_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DeniedKernel32:
        def OpenProcess(self, access: int, inherit: bool, pid: int) -> int:
            assert access == PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
            assert not inherit
            assert pid == 12345
            ctypes.set_last_error(ERROR_ACCESS_DENIED)
            return 0

    monkeypatch.setattr(win32_backend, "kernel32", DeniedKernel32())
    identity = ProcessIdentity(12345, "target.exe", 1.0, None, Architecture.X64)
    with pytest.raises(AccessDeniedError, match="PID 12345"):
        Win32MemoryBackend().open(identity, AccessMode.READ)


def test_read_current_process_and_invalid_address_is_safe() -> None:
    value = ctypes.c_int32(0x12345678)
    backend = Win32MemoryBackend()
    backend.open(current_identity(), AccessMode.READ)
    try:
        raw = backend.read(ctypes.addressof(value), ctypes.sizeof(value))
        assert struct.unpack("=i", raw) == (0x12345678,)

        invalid_target = bytearray(16)
        assert backend.read_into(0x1, memoryview(invalid_target)) == 0
        assert invalid_target == bytes(16)
    finally:
        backend.close()
        backend.close()
    assert not backend.is_open


def test_read_only_write_is_rejected_before_address_validation() -> None:
    backend = Win32MemoryBackend()
    backend.open(current_identity(), AccessMode.READ)
    try:
        with pytest.raises(WriteNotPermittedError):
            backend.write(0x1, b"x")
    finally:
        backend.close()


def test_invalid_write_address_is_rejected() -> None:
    backend = Win32MemoryBackend()
    backend.open(current_identity(), AccessMode.READ_WRITE)
    try:
        with pytest.raises(InvalidAddressError):
            backend.write(0x1, b"x")
    finally:
        backend.close()


def test_process_service_rejects_reserved_and_denylisted_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ProcessService()
    with pytest.raises(ProcessNotAllowedError):
        service.identity(0)
    with pytest.raises(ProcessNotAllowedError):
        service.identity(4)

    class ProtectedProcess:
        def name(self) -> str:
            return "lsass.exe"

        def create_time(self) -> float:
            return 1.0

    monkeypatch.setattr(psutil, "Process", lambda _pid: ProtectedProcess())
    with pytest.raises(ProcessNotAllowedError):
        service.identity(12345)


def test_numeric_process_filter_is_exact_and_own_process_is_not_attachable() -> None:
    entries = ProcessService().list_processes(str(os.getpid()), include_system=True)
    assert len(entries) == 1
    assert entries[0].pid == os.getpid()
    assert not entries[0].can_attach
    assert entries[0].is_system
