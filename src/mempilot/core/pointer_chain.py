"""Pointer-chain models and safe resolution helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from mempilot.core.backend import MemoryBackend, ModuleInfo
from mempilot.core.data_types import DataType, format_hex
from mempilot.i18n import t


class PointerChain(BaseModel):
    """Persistable module-relative pointer chain."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    module: str
    base_offset: int
    offsets: list[int]
    data_type: DataType


@dataclass(frozen=True, slots=True)
class ChainStep:
    index: int
    address: int
    pointer_value: int | None
    ok: bool
    note: str


@dataclass(frozen=True, slots=True)
class ChainResolution:
    steps: list[ChainStep]
    final_address: int | None
    error: str | None


def _format_address(address: int) -> str:
    return format_hex(address) if address >= 0 else f"-0x{-address:X}"


def resolve_chain(
    chain: PointerChain,
    backend: MemoryBackend,
    modules: Sequence[ModuleInfo],
) -> ChainResolution:
    """Resolve a chain and return partial diagnostic steps instead of raising."""
    module = next(
        (
            candidate
            for candidate in modules
            if candidate.name.casefold() == chain.module.casefold()
        ),
        None,
    )
    if module is None:
        return ChainResolution([], None, t("pointer.module_not_loaded", module=repr(chain.module)))
    address = module.base + chain.base_offset
    steps: list[ChainStep] = []
    try:
        pointer_size = backend.pointer_size
    except Exception:
        return ChainResolution(
            [], None, t("pointer.read_failed_at", address=_format_address(address))
        )
    for index, offset in enumerate(chain.offsets, start=1):
        try:
            raw = backend.read(address, pointer_size)
        except Exception:
            steps.append(ChainStep(index, address, None, False, t("pointer.read_failed")))
            return ChainResolution(
                steps,
                None,
                t("pointer.read_failed_at", address=_format_address(address)),
            )
        if len(raw) != pointer_size:
            steps.append(ChainStep(index, address, None, False, t("pointer.partial_read")))
            return ChainResolution(
                steps,
                None,
                t("pointer.read_failed_at", address=_format_address(address)),
            )
        pointer = int.from_bytes(raw, byteorder="little", signed=False)
        if pointer == 0:
            steps.append(ChainStep(index, address, pointer, False, t("pointer.null")))
            return ChainResolution(
                steps,
                None,
                t("pointer.null_at_step", step=index),
            )
        steps.append(ChainStep(index, address, pointer, True, t("pointer.resolved")))
        address = pointer + offset
    return ChainResolution(steps, address, None)


def address_to_module_offset(address: int, modules: Sequence[ModuleInfo]) -> tuple[str, int] | None:
    """Convert an absolute address to the containing module and offset."""
    for module in modules:
        if module.contains(address):
            return module.name, address - module.base
    return None
