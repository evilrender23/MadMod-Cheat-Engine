"""Abstract memory backend and shared process data structures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from types import TracebackType
from typing import Self

from mempilot.core.exceptions import MemoryReadError, NotAttachedError


class Architecture(StrEnum):
    X64 = "x64"
    X86 = "x86"
    ARM64 = "arm64"
    UNKNOWN = "desconocida"


class AccessMode(StrEnum):
    READ = "read"
    READ_WRITE = "read_write"


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    name: str
    create_time: float
    path: str | None
    architecture: Architecture

    def matches(self, other: ProcessIdentity) -> bool:
        """Return whether two observations identify the same process instance."""
        return self.pid == other.pid and self.create_time == other.create_time


_READABLE = frozenset({0x02, 0x04, 0x08, 0x20, 0x40, 0x80})
_WRITABLE = frozenset({0x04, 0x08, 0x40, 0x80})
_EXECUTABLE = frozenset({0x10, 0x20, 0x40, 0x80})
_PAGE_GUARD = 0x100
_MEM_PRIVATE = 0x20000
_MEM_MAPPED = 0x40000
_MEM_IMAGE = 0x1000000


@dataclass(frozen=True, slots=True)
class MemoryRegion:
    base: int
    size: int
    protect: int
    state: int
    type: int
    module: str | None = None

    @property
    def end(self) -> int:
        return self.base + self.size

    @property
    def readable(self) -> bool:
        return not bool(self.protect & _PAGE_GUARD) and self.protect & 0xFF in _READABLE

    @property
    def writable(self) -> bool:
        return not bool(self.protect & _PAGE_GUARD) and self.protect & 0xFF in _WRITABLE

    @property
    def executable(self) -> bool:
        return self.protect & 0xFF in _EXECUTABLE

    def protect_text(self) -> str:
        """Return compact protection flags for display."""
        base = self.protect & 0xFF
        if base == 0x01:
            text = "NA"
        elif base in {0x08, 0x80}:
            text = "WC"
        else:
            text = ""
            if self.readable:
                text += "R"
            if self.writable:
                text += "W"
            if self.executable:
                text += "X"
            if not text:
                text = "NA"
        return f"{text}+G" if self.protect & _PAGE_GUARD else text

    def type_text(self) -> str:
        """Return the Spanish region category."""
        return {
            _MEM_PRIVATE: "Privada",
            _MEM_IMAGE: "Imagen",
            _MEM_MAPPED: "Mapeada",
        }.get(self.type, "Desconocida")


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    name: str
    path: str
    base: int
    size: int

    def contains(self, address: int) -> bool:
        return self.base <= address < self.base + self.size


class MemoryBackend(ABC):
    """Backend contract used by scans, watches, and the controller."""

    @abstractmethod
    def open(self, identity: ProcessIdentity, mode: AccessMode) -> None:
        """Open a process with the requested access mode."""

    @abstractmethod
    def close(self) -> None:
        """Close the process handle idempotently."""

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """Return whether a process handle is open."""

    @property
    @abstractmethod
    def mode(self) -> AccessMode | None:
        """Return the current access mode."""

    @property
    @abstractmethod
    def identity(self) -> ProcessIdentity | None:
        """Return the process identity bound to the open handle."""

    @abstractmethod
    def is_alive(self) -> bool:
        """Return whether the bound process still exists."""

    @abstractmethod
    def regions(self) -> list[MemoryRegion]:
        """Return committed readable memory regions."""

    @abstractmethod
    def modules(self) -> list[ModuleInfo]:
        """Return loaded process modules."""

    def read(self, address: int, size: int) -> bytes:
        """Read an exact UI-sized memory span or raise on total failure."""
        if size < 0:
            raise ValueError("El tamaño de lectura no puede ser negativo")
        target = bytearray(size)
        count = self.read_into(address, memoryview(target))
        if size and count == 0:
            raise MemoryReadError(
                f"No se pudo leer la dirección 0x{address:016X}. Comprueba que siga asignada."
            )
        return bytes(target[:count])

    @abstractmethod
    def read_into(self, address: int, buffer: memoryview) -> int:
        """Read into an existing buffer, returning zero on total failure."""

    @abstractmethod
    def write(self, address: int, data: bytes) -> int:
        """Write data and return the number of bytes written."""

    @property
    def pointer_size(self) -> int:
        identity = self.identity
        if identity is None:
            raise NotAttachedError()
        return 4 if identity.architecture is Architecture.X86 else 8

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
