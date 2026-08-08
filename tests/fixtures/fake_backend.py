"""Deterministic in-memory backend used by cross-platform unit tests."""

from __future__ import annotations

from dataclasses import dataclass

from mempilot.core.backend import (
    AccessMode,
    MemoryBackend,
    MemoryRegion,
    ModuleInfo,
    ProcessIdentity,
)
from mempilot.core.exceptions import (
    InvalidAddressError,
    MemoryWriteError,
    NotAttachedError,
    WriteNotPermittedError,
)

_MEM_COMMIT = 0x1000
_MEM_PRIVATE = 0x20000
_WRITABLE = frozenset({0x04, 0x08, 0x40, 0x80})


@dataclass(slots=True)
class _RegionStorage:
    base: int
    data: bytearray
    protect: int

    @property
    def end(self) -> int:
        return self.base + len(self.data)


class FakeMemoryBackend(MemoryBackend):
    """In-memory bytearray backend for scanner tests on every platform."""

    def __init__(
        self,
        regions: list[tuple[int, bytearray, int]],
        identity: ProcessIdentity,
    ) -> None:
        self._regions = [_RegionStorage(base, data, protect) for base, data, protect in regions]
        self._regions.sort(key=lambda region: region.base)
        self._identity: ProcessIdentity | None = identity
        self._mode: AccessMode | None = AccessMode.READ_WRITE
        self._open = True
        self._alive = True
        self._modules: list[ModuleInfo] = []
        self.read_into_calls = 0

    def open(self, identity: ProcessIdentity, mode: AccessMode) -> None:
        self._identity = identity
        self._mode = mode
        self._open = True
        self._alive = True

    def close(self) -> None:
        self._open = False
        self._mode = None
        self._identity = None

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def mode(self) -> AccessMode | None:
        return self._mode

    @property
    def identity(self) -> ProcessIdentity | None:
        return self._identity

    def is_alive(self) -> bool:
        return self._open and self._alive

    def set_alive(self, alive: bool) -> None:
        """Simulate process exit without closing the retained handle."""
        self._alive = alive

    def regions(self) -> list[MemoryRegion]:
        self._require_open()
        return [
            MemoryRegion(
                base=region.base,
                size=len(region.data),
                protect=region.protect,
                state=_MEM_COMMIT,
                type=_MEM_PRIVATE,
            )
            for region in self._regions
        ]

    def modules(self) -> list[ModuleInfo]:
        self._require_open()
        return list(self._modules)

    def set_modules(self, modules: list[ModuleInfo]) -> None:
        """Provide module metadata for pointer and display tests."""
        self._modules = list(modules)

    def read_into(self, address: int, buffer: memoryview) -> int:
        self.read_into_calls += 1
        if not self._open or not self._alive or address < 0:
            return 0
        region = self._find_region(address)
        if region is None:
            return 0
        count = min(len(buffer), region.end - address)
        if count <= 0:
            return 0
        start = address - region.base
        buffer[:count] = region.data[start : start + count]
        return count

    def write(self, address: int, data: bytes) -> int:
        self._require_open()
        if self._mode is AccessMode.READ:
            raise WriteNotPermittedError()
        region = self._find_region(address)
        if region is None or address + len(data) > region.end:
            raise InvalidAddressError()
        if region.protect & 0xFF not in _WRITABLE:
            raise MemoryWriteError("La región simulada no permite escritura.")
        start = address - region.base
        region.data[start : start + len(data)] = data
        return len(data)

    def poke(self, address: int, data: bytes) -> None:
        """Mutate memory directly to simulate a process-side value change."""
        region = self._find_region(address)
        if region is None or address + len(data) > region.end:
            raise InvalidAddressError()
        start = address - region.base
        region.data[start : start + len(data)] = data

    def _find_region(self, address: int) -> _RegionStorage | None:
        return next(
            (region for region in self._regions if region.base <= address < region.end),
            None,
        )

    def _require_open(self) -> None:
        if not self._open:
            raise NotAttachedError()
