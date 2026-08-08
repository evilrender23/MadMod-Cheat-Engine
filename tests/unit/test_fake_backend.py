"""Behavioral contract of the cross-platform in-memory backend."""

from __future__ import annotations

import pytest
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.core.backend import AccessMode, Architecture, ProcessIdentity
from mempilot.core.exceptions import InvalidAddressError, WriteNotPermittedError

IDENTITY = ProcessIdentity(9090, "fake.exe", 6.0, None, Architecture.X64)


def test_read_write_poke_and_partial_read() -> None:
    backend = FakeMemoryBackend([(0x1000, bytearray(b"abcdefgh"), 0x04)], IDENTITY)
    target = bytearray(6)

    assert backend.read_into(0x1006, memoryview(target)) == 2
    assert bytes(target[:2]) == b"gh"
    assert backend.write(0x1002, b"XY") == 2
    assert backend.read(0x1000, 8) == b"abXYefgh"
    backend.poke(0x1004, b"ZZ")
    assert backend.read(0x1000, 8) == b"abXYZZgh"
    assert backend.read_into(0x9999, memoryview(target)) == 0


def test_read_only_mode_and_invalid_address_are_rejected() -> None:
    backend = FakeMemoryBackend([(0x1000, bytearray(8), 0x04)], IDENTITY)
    backend.open(IDENTITY, AccessMode.READ)

    with pytest.raises(WriteNotPermittedError):
        backend.write(0x1000, b"x")

    backend.open(IDENTITY, AccessMode.READ_WRITE)
    with pytest.raises(InvalidAddressError):
        backend.write(0x2000, b"x")
