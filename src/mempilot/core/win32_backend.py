"""Concrete Win32 implementation of the memory backend contract."""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from dataclasses import replace

from mempilot.core.backend import (
    AccessMode,
    Architecture,
    MemoryBackend,
    MemoryRegion,
    ModuleInfo,
    ProcessIdentity,
)
from mempilot.core.exceptions import (
    AccessDeniedError,
    InvalidAddressError,
    MemoryWriteError,
    NotAttachedError,
    ProcessNotFoundError,
    WriteNotPermittedError,
)
from mempilot.core.memory_regions import (
    enumerate_modules,
    enumerate_readable_regions,
    is_committed_writable,
    query_region,
)
from mempilot.core.win32_api import (
    ERROR_ACCESS_DENIED,
    IMAGE_FILE_MACHINE,
    PROCESS_QUERY_INFORMATION,
    PROCESS_VM_OPERATION,
    PROCESS_VM_READ,
    PROCESS_VM_WRITE,
    STILL_ACTIVE,
    kernel32,
)


def architecture_from_handle(handle: int) -> Architecture:
    """Detect native and WOW64 process architecture with IsWow64Process2."""
    process_machine = wintypes.WORD()
    native_machine = wintypes.WORD()
    if not kernel32.IsWow64Process2(
        handle,
        ctypes.byref(process_machine),
        ctypes.byref(native_machine),
    ):
        return Architecture.UNKNOWN
    if process_machine.value != 0:
        return Architecture.X86
    return IMAGE_FILE_MACHINE.get(int(native_machine.value), Architecture.UNKNOWN)


class Win32MemoryBackend(MemoryBackend):
    """Memory backend backed by a retained Windows process handle."""

    def __init__(self) -> None:
        self._handle: int | None = None
        self._mode: AccessMode | None = None
        self._identity: ProcessIdentity | None = None
        self._lock = threading.RLock()

    def open(self, identity: ProcessIdentity, mode: AccessMode) -> None:
        """Open with the minimum exact access mask required by the requested mode."""
        self.close()
        access = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
        if mode is AccessMode.READ_WRITE:
            access |= PROCESS_VM_WRITE | PROCESS_VM_OPERATION
        ctypes.set_last_error(0)
        raw_handle = kernel32.OpenProcess(access, False, identity.pid)
        if not raw_handle:
            error = ctypes.get_last_error()
            if error == ERROR_ACCESS_DENIED:
                raise AccessDeniedError(
                    f"Acceso denegado al PID {identity.pid}. Ejecuta M@D-Engine como administrador "
                    "o elige un proceso de tu mismo nivel de integridad."
                )
            raise ProcessNotFoundError(
                f"No se pudo abrir el PID {identity.pid}. Actualiza la lista y vuelve a intentarlo."
            )
        handle = int(raw_handle)
        detected = architecture_from_handle(handle)
        bound_identity = replace(identity, architecture=detected)
        with self._lock:
            self._handle = handle
            self._mode = mode
            self._identity = bound_identity

    def close(self) -> None:
        """Close the retained process handle exactly once."""
        with self._lock:
            handle = self._handle
            if handle is None:
                return
            self._handle = None
            self._mode = None
            self._identity = None
            kernel32.CloseHandle(handle)

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._handle is not None

    @property
    def mode(self) -> AccessMode | None:
        with self._lock:
            return self._mode

    @property
    def identity(self) -> ProcessIdentity | None:
        with self._lock:
            return self._identity

    def is_alive(self) -> bool:
        with self._lock:
            handle = self._handle
            if handle is None:
                return False
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return int(exit_code.value) == STILL_ACTIVE

    def regions(self) -> list[MemoryRegion]:
        with self._lock:
            handle = self._require_handle()
            loaded_modules = enumerate_modules(handle)
            return enumerate_readable_regions(handle, loaded_modules)

    def modules(self) -> list[ModuleInfo]:
        with self._lock:
            return enumerate_modules(self._require_handle())

    def read_into(self, address: int, buffer: memoryview) -> int:
        """Read without allocating and return zero on every total read failure."""
        if buffer.readonly:
            raise ValueError("El búfer de lectura debe ser modificable")
        view = buffer.cast("B")
        size = view.nbytes
        if size == 0:
            return 0
        if address < 0:
            return 0
        with self._lock:
            handle = self._require_handle()
            target = (ctypes.c_ubyte * size).from_buffer(view)
            copied = ctypes.c_size_t()
            kernel32.ReadProcessMemory(
                handle,
                ctypes.c_void_p(address),
                target,
                size,
                ctypes.byref(copied),
            )
            return min(int(copied.value), size)

    def write(self, address: int, data: bytes) -> int:
        with self._lock:
            handle = self._require_handle()
            if self._mode is AccessMode.READ:
                raise WriteNotPermittedError(
                    "La sesión es de solo lectura. Vuelve a adjuntarte con permiso de escritura."
                )
            if not data:
                return 0
            region = query_region(handle, address)
            if not is_committed_writable(region, address, len(data)):
                raise InvalidAddressError(
                    f"La dirección 0x{address:016X} no pertenece a una región asignada y "
                    "escribible. Actualiza los resultados e inténtalo de nuevo."
                )
            source = ctypes.create_string_buffer(data, len(data))
            copied = ctypes.c_size_t()
            ok = kernel32.WriteProcessMemory(
                handle,
                ctypes.c_void_p(address),
                source,
                len(data),
                ctypes.byref(copied),
            )
            written = int(copied.value)
            if not ok or written != len(data):
                raise MemoryWriteError(
                    f"No se pudo escribir la dirección 0x{address:016X}. "
                    "Comprueba la protección de la región y vuelve a intentarlo."
                )
            return written

    def _require_handle(self) -> int:
        handle = self._handle
        if handle is None:
            raise NotAttachedError()
        return handle
