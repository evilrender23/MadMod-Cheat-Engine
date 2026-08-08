"""Safe pointer-chain resolution and module conversion."""

from __future__ import annotations

from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.core.backend import Architecture, ModuleInfo, ProcessIdentity
from mempilot.core.data_types import DataType
from mempilot.core.pointer_chain import (
    PointerChain,
    address_to_module_offset,
    resolve_chain,
)

IDENTITY = ProcessIdentity(8080, "chain.exe", 5.0, None, Architecture.X64)
MODULE = ModuleInfo("chain.exe", "C:/chain.exe", 0x1000, 0x5000)


def chain() -> PointerChain:
    return PointerChain(
        id="chain-1",
        label="Vida",
        module="CHAIN.EXE",
        base_offset=0x100,
        offsets=[0x10, 0x20, 0x30],
        data_type=DataType.INT32,
    )


def backend_with_chain(*, null_second: bool = False) -> FakeMemoryBackend:
    memory = bytearray(0x5000)
    backend = FakeMemoryBackend([(0x1000, memory, 0x04)], IDENTITY)
    backend.poke(0x1100, (0x2000).to_bytes(8, "little"))
    backend.poke(0x2010, (0 if null_second else 0x3000).to_bytes(8, "little"))
    backend.poke(0x3020, (0x4000).to_bytes(8, "little"))
    return backend


def test_resolves_three_pointer_steps() -> None:
    resolution = resolve_chain(chain(), backend_with_chain(), [MODULE])

    assert resolution.error is None
    assert resolution.final_address == 0x4030
    assert [step.pointer_value for step in resolution.steps] == [0x2000, 0x3000, 0x4000]
    assert all(step.ok for step in resolution.steps)


def test_null_pointer_returns_partial_steps_without_raising() -> None:
    resolution = resolve_chain(chain(), backend_with_chain(null_second=True), [MODULE])

    assert resolution.final_address is None
    assert resolution.error == "puntero nulo en el paso 2"
    assert len(resolution.steps) == 2
    assert resolution.steps[-1].ok is False


def test_missing_module_and_failed_read_are_structured_errors() -> None:
    missing = resolve_chain(chain(), backend_with_chain(), [])
    backend = backend_with_chain()
    backend.close()
    failed = resolve_chain(chain(), backend, [MODULE])

    assert missing.error == "módulo 'CHAIN.EXE' no cargado"
    assert missing.steps == []
    assert failed.error is not None
    assert failed.final_address is None


def test_address_to_module_offset() -> None:
    assert address_to_module_offset(0x1234, [MODULE]) == ("chain.exe", 0x234)
    assert address_to_module_offset(0x9000, [MODULE]) is None
