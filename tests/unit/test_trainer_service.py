"""Persistent trainer catalogs and reversible controller activation contracts."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from tests.fixtures.fake_backend import FakeMemoryBackend

from mempilot.config.settings import Settings, UISettings
from mempilot.controller import Actor, AppController
from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.data_types import DataType
from mempilot.core.exceptions import TrainerError
from mempilot.core.watcher import WatchEntry, WatchSpec
from mempilot.services.audit_service import AuditService
from mempilot.services.trainer_service import TrainerService, TrickMode

_ADDRESS = 0x1020


def _identity(create_time: float = 10.0) -> ProcessIdentity:
    return ProcessIdentity(
        4242,
        "Memory Lab.exe",
        create_time,
        "C:/Games/Memory Lab.exe",
        Architecture.X64,
    )


def _controller(
    tmp_path: Path,
    *,
    initial_value: int = 100,
    create_time: float = 10.0,
) -> tuple[AppController, FakeMemoryBackend]:
    identity = _identity(create_time)
    memory = bytearray(256)
    struct.pack_into("<i", memory, _ADDRESS - 0x1000, initial_value)
    backend = FakeMemoryBackend([(0x1000, memory, 0x04)], identity)
    controller = AppController(
        backend,
        audit_service=AuditService(tmp_path / f"audit-{create_time}.jsonl"),
        trainer_service=TrainerService(tmp_path / "trainers"),
        settings=Settings(ui=UISettings(watch_refresh_ms=50, results_refresh_ms=50)),
    )
    controller.attach(identity.pid, True, Actor.USER)
    return controller, backend


def test_catalog_is_process_bound_versioned_and_excludes_runtime_state(tmp_path: Path) -> None:
    service = TrainerService(tmp_path / "trainers")
    identity = _identity()

    trick = service.save_trick(
        identity,
        name="Vida infinita",
        watch=WatchEntry.from_spec(
            WatchSpec("Vida", DataType.INT32, address=_ADDRESS, interval_ms=75)
        ),
        enabled_value="100",
        disabled_value=None,
        mode=TrickMode.FREEZE,
        interval_ms=75,
        notes="Probado en Memory Lab.",
    )

    loaded = service.load(identity)
    assert loaded.process_name == "Memory Lab.exe"
    assert loaded.tricks == [trick]
    raw = next((tmp_path / "trainers").rglob("trainer.json")).read_text(encoding="utf-8")
    document = json.loads(raw)
    assert document["schema_version"] == 1
    assert "pid" not in raw
    assert "current_value" not in raw
    assert "frozen" not in raw


def test_catalog_path_stays_confined_for_hostile_process_name(tmp_path: Path) -> None:
    service = TrainerService(tmp_path / "trainers")
    identity = ProcessIdentity(
        9,
        "../../outside.exe",
        1.0,
        "C:/safe/outside.exe",
        Architecture.X64,
    )

    service.save_trick(
        identity,
        name="Seguro",
        watch=WatchEntry.from_spec(WatchSpec("Valor", DataType.INT32, address=_ADDRESS)),
        enabled_value="1",
        disabled_value=None,
        mode=TrickMode.FREEZE,
        interval_ms=100,
        notes="",
    )

    files = list((tmp_path / "trainers").rglob("trainer.json"))
    assert len(files) == 1
    assert files[0].resolve().is_relative_to((tmp_path / "trainers").resolve())


def test_write_pair_requires_a_disabled_value(tmp_path: Path) -> None:
    service = TrainerService(tmp_path / "trainers")

    with pytest.raises(TrainerError, match="desactivado"):
        service.save_trick(
            _identity(),
            name="Velocidad",
            watch=WatchEntry.from_spec(WatchSpec("Velocidad", DataType.INT32, address=_ADDRESS)),
            enabled_value="2",
            disabled_value=None,
            mode=TrickMode.WRITE_PAIR,
            interval_ms=100,
            notes="",
        )


def test_controller_saves_only_the_tested_value_and_freeze_is_reversible(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    controller, backend = _controller(tmp_path)
    try:
        watch = controller.add_watch(
            WatchSpec("Vida", DataType.INT32, address=_ADDRESS, interval_ms=50),
            Actor.USER,
        )
        with pytest.raises(TrainerError, match="valor activado"):
            controller.save_trainer_trick(
                watch.id,
                name="Vida infinita",
                enabled_value="250",
                disabled_value=None,
                mode=TrickMode.FREEZE,
                interval_ms=50,
                notes="",
                actor=Actor.USER,
            )

        trick = controller.save_trainer_trick(
            watch.id,
            name="Vida infinita",
            enabled_value="100",
            disabled_value=None,
            mode=TrickMode.FREEZE,
            interval_ms=50,
            notes="Confirmado por el usuario.",
            actor=Actor.USER,
        )
        assert controller.list_trainer_tricks()[0].active is True

        backend.poke(_ADDRESS, struct.pack("<i", 73))
        qtbot.waitUntil(
            lambda: struct.unpack("<i", backend.read(_ADDRESS, 4))[0] == 100,
            timeout=3000,
        )

        assert not controller.set_trainer_trick_active(trick.id, False, Actor.USER).active
        backend.poke(_ADDRESS, struct.pack("<i", 73))
        qtbot.wait(120)
        assert struct.unpack("<i", backend.read(_ADDRESS, 4))[0] == 73
    finally:
        controller.shutdown()


def test_saved_write_pair_reloads_for_same_executable_and_restores_disabled_value(
    tmp_path: Path,
) -> None:
    first, _backend = _controller(tmp_path)
    try:
        watch = first.add_watch(
            WatchSpec("Multiplicador", DataType.INT32, address=_ADDRESS),
            Actor.USER,
        )
        trick = first.save_trainer_trick(
            watch.id,
            name="Daño doble",
            enabled_value="100",
            disabled_value="25",
            mode=TrickMode.WRITE_PAIR,
            interval_ms=100,
            notes="",
            actor=Actor.USER,
        )
    finally:
        first.shutdown()

    second, backend = _controller(tmp_path, initial_value=25, create_time=20.0)
    try:
        state = second.list_trainer_tricks()[0]
        assert state.trick.id == trick.id
        assert state.active is False

        assert second.set_trainer_trick_active(trick.id, True, Actor.USER).active
        assert struct.unpack("<i", backend.read(_ADDRESS, 4))[0] == 100
        assert not second.set_trainer_trick_active(trick.id, False, Actor.USER).active
        assert struct.unpack("<i", backend.read(_ADDRESS, 4))[0] == 25
    finally:
        second.shutdown()
