"""Win32 memory-region and module enumeration helpers."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path

from mempilot.core.backend import MemoryRegion, ModuleInfo
from mempilot.core.win32_api import (
    LIST_MODULES_ALL,
    MAX_USER_ADDRESS,
    MEM_COMMIT,
    MEMORY_BASIC_INFORMATION64,
    MODULEINFO,
    PAGE_GUARD,
    READABLE_PROTECTIONS,
    WRITABLE_PROTECTIONS,
    kernel32,
    psapi,
)

_INITIAL_MODULE_CAPACITY = 256
_MAX_PATH_CHARS = 32_768


def enumerate_modules(handle: int) -> list[ModuleInfo]:
    """Return all modules visible through PSAPI, or an empty list if unavailable."""
    capacity = _INITIAL_MODULE_CAPACITY
    handles: ctypes.Array[wintypes.HMODULE]
    while True:
        handles = (wintypes.HMODULE * capacity)()
        bytes_needed = wintypes.DWORD()
        ok = psapi.EnumProcessModulesEx(
            handle,
            handles,
            ctypes.sizeof(handles),
            ctypes.byref(bytes_needed),
            LIST_MODULES_ALL,
        )
        if not ok:
            return []
        count = int(bytes_needed.value) // ctypes.sizeof(wintypes.HMODULE)
        if count <= capacity:
            break
        capacity = count

    modules: list[ModuleInfo] = []
    for index in range(count):
        module_handle = handles[index]
        path_buffer = ctypes.create_unicode_buffer(_MAX_PATH_CHARS)
        path_length = psapi.GetModuleFileNameExW(
            handle,
            module_handle,
            path_buffer,
            len(path_buffer),
        )
        if path_length == 0:
            continue
        info = MODULEINFO()
        if not psapi.GetModuleInformation(
            handle,
            module_handle,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            continue
        path = path_buffer.value
        modules.append(
            ModuleInfo(
                name=Path(path).name,
                path=path,
                base=int(info.lpBaseOfDll or 0),
                size=int(info.SizeOfImage),
            )
        )
    modules.sort(key=lambda module: module.base)
    return modules


def query_region(handle: int, address: int) -> MemoryRegion | None:
    """Return the virtual-memory region containing an address."""
    if address < 0 or address > MAX_USER_ADDRESS:
        return None
    info = MEMORY_BASIC_INFORMATION64()
    result = kernel32.VirtualQueryEx(
        handle,
        ctypes.c_void_p(address),
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if result == 0 or int(info.RegionSize) <= 0:
        return None
    return MemoryRegion(
        base=int(info.BaseAddress or 0),
        size=int(info.RegionSize),
        protect=int(info.Protect),
        state=int(info.State),
        type=int(info.Type),
    )


def enumerate_readable_regions(
    handle: int,
    modules: list[ModuleInfo] | None = None,
) -> list[MemoryRegion]:
    """Walk committed, readable, non-guarded regions up to the user address ceiling."""
    known_modules = enumerate_modules(handle) if modules is None else modules
    regions: list[MemoryRegion] = []
    address = 0
    while address <= MAX_USER_ADDRESS:
        info = MEMORY_BASIC_INFORMATION64()
        result = kernel32.VirtualQueryEx(
            handle,
            ctypes.c_void_p(address),
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if result == 0:
            break
        base = int(info.BaseAddress or 0)
        size = int(info.RegionSize)
        if size <= 0:
            break
        next_address = base + size
        if next_address <= address:
            break
        protect = int(info.Protect)
        if (
            int(info.State) == MEM_COMMIT
            and not protect & PAGE_GUARD
            and protect & 0xFF in READABLE_PROTECTIONS
        ):
            module_name = next(
                (module.name for module in known_modules if module.contains(base)),
                None,
            )
            regions.append(
                MemoryRegion(
                    base=base,
                    size=size,
                    protect=protect,
                    state=int(info.State),
                    type=int(info.Type),
                    module=module_name,
                )
            )
        address = next_address
    return regions


def is_committed_writable(region: MemoryRegion | None, address: int, size: int) -> bool:
    """Return whether a complete span lies in one committed writable region."""
    if region is None or size < 0 or address < region.base:
        return False
    if region.state != MEM_COMMIT or region.protect & PAGE_GUARD:
        return False
    if region.protect & 0xFF not in WRITABLE_PROTECTIONS:
        return False
    return address + size <= region.end
