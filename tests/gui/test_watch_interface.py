"""Focused GUI contracts for watch editing and pointer-chain resolution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QDialog, QFileDialog
from pytestqt.qtbot import QtBot

from mempilot.controller import Actor, AppController
from mempilot.core.backend import ModuleInfo
from mempilot.core.data_types import DataType
from mempilot.core.pointer_chain import ChainResolution, ChainStep, PointerChain
from mempilot.core.watcher import WatchEntry, WatchSpec
from mempilot.i18n import t
from mempilot.ui.dialogs.pointer_dialog import PointerDialog
from mempilot.ui.models.watch_model import WatchColumn, WatchModel
from mempilot.ui.theme import AMBER_TINT
from mempilot.ui.widgets.watch_view import WatchView


class FakeWatchController(QObject):
    """Signal-compatible facade double recording every public call."""

    watches_changed = Signal()
    watch_values = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.entries = [
            WatchEntry(
                id="watch-1",
                label="Salud",
                data_type=DataType.INT32,
                address=0x1234,
                interval_ms=100,
                desired_value="100",
                current_value="95",
            )
        ]
        self.calls: list[tuple[object, ...]] = []
        self.modules = [
            ModuleInfo(
                name="memory_lab.exe",
                path="C:/Memory Lab/memory_lab.exe",
                base=0x140000000,
                size=0x100000,
            )
        ]
        self.resolution = ChainResolution(
            steps=[
                ChainStep(
                    index=0,
                    address=0x140001000,
                    pointer_value=0x200000000,
                    ok=True,
                    note="",
                ),
                ChainStep(
                    index=1,
                    address=0x200000020,
                    pointer_value=0x300000000,
                    ok=True,
                    note="",
                ),
            ],
            final_address=0x300000008,
            error=None,
        )
        self.added_specs: list[WatchSpec] = []

    def list_watches(self) -> list[WatchEntry]:
        return [replace(entry) for entry in self.entries]

    def update_watch(
        self,
        watch_id: str,
        *,
        label: str | None = None,
        desired_value: str | None = None,
        interval_ms: int | None = None,
        notes: str | None = None,
        actor: Actor = Actor.USER,
    ) -> None:
        self.calls.append(
            (
                "update_watch",
                watch_id,
                label,
                desired_value,
                interval_ms,
                notes,
                actor,
            )
        )
        entry = self._entry(watch_id)
        if label is not None:
            entry.label = label
        if desired_value is not None:
            entry.desired_value = desired_value
        if interval_ms is not None:
            entry.interval_ms = interval_ms
        if notes is not None:
            entry.notes = notes
        self.watches_changed.emit()

    def set_watch_value(self, watch_id: str, value: str, actor: Actor) -> None:
        self.calls.append(("set_watch_value", watch_id, value, actor))
        entry = self._entry(watch_id)
        entry.current_value = value
        entry.desired_value = value
        self.watches_changed.emit()

    def set_freeze(
        self,
        watch_id: str,
        frozen: bool,
        value: str | None,
        interval_ms: int,
        actor: Actor,
    ) -> None:
        self.calls.append(("set_freeze", watch_id, frozen, value, interval_ms, actor))
        entry = self._entry(watch_id)
        entry.frozen = frozen
        entry.desired_value = value
        entry.interval_ms = interval_ms
        self.watches_changed.emit()

    def remove_watch(self, watch_id: str, actor: Actor) -> None:
        self.calls.append(("remove_watch", watch_id, actor))
        self.entries = [entry for entry in self.entries if entry.id != watch_id]
        self.watches_changed.emit()

    def add_watch(self, spec: WatchSpec, actor: Actor) -> WatchEntry:
        self.calls.append(("add_watch", spec, actor))
        self.added_specs.append(spec)
        entry = WatchEntry.from_spec(spec, watch_id=f"watch-{len(self.entries) + 1}")
        self.entries.append(entry)
        self.watches_changed.emit()
        return replace(entry)

    def list_modules(self, actor: Actor = Actor.USER) -> list[ModuleInfo]:
        self.calls.append(("list_modules", actor))
        return list(self.modules)

    def resolve_chain(self, chain: PointerChain) -> ChainResolution:
        self.calls.append(("resolve_chain", chain))
        return self.resolution

    def read_address(self, address: int, data_type: DataType) -> str:
        self.calls.append(("read_address", address, data_type))
        return "777"

    def save_workspace(self, path: Path, actor: Actor) -> None:
        self.calls.append(("save_workspace", path, actor))

    def load_workspace(self, path: Path, actor: Actor) -> None:
        self.calls.append(("load_workspace", path, actor))
        self.watches_changed.emit()

    def _entry(self, watch_id: str) -> WatchEntry:
        return next(entry for entry in self.entries if entry.id == watch_id)


@pytest.mark.gui
def test_watch_model_has_eight_columns_and_routes_every_edit(qtbot: QtBot) -> None:
    fake = FakeWatchController()
    controller = cast(AppController, fake)
    model = WatchModel(controller)

    assert model.columnCount() == 8
    assert [
        model.headerData(column, Qt.Orientation.Horizontal) for column in range(model.columnCount())
    ] == [
        "Nombre",
        "Dirección",
        "Tipo",
        "Valor",
        "Deseado",
        "Congelado",
        "Intervalo",
        "Notas",
    ]

    assert model.setData(model.index(0, WatchColumn.NAME), "Vida")
    assert fake.calls[-1] == (
        "update_watch",
        "watch-1",
        "Vida",
        None,
        None,
        None,
        Actor.USER,
    )
    assert model.setData(model.index(0, WatchColumn.VALUE), "250")
    assert fake.calls[-1] == ("set_watch_value", "watch-1", "250", Actor.USER)
    assert model.setData(model.index(0, WatchColumn.DESIRED), "100")
    assert fake.calls[-1][0:4] == ("update_watch", "watch-1", None, "100")
    assert model.setData(model.index(0, WatchColumn.INTERVAL), "250")
    assert fake.calls[-1][0:6] == (
        "update_watch",
        "watch-1",
        None,
        None,
        250,
        None,
    )
    assert model.setData(model.index(0, WatchColumn.NOTES), "Valor estable")
    assert fake.calls[-1][0] == "update_watch"
    assert fake.calls[-1][5] == "Valor estable"

    frozen_index = model.index(0, WatchColumn.FROZEN)
    assert model.setData(frozen_index, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert fake.calls[-1] == (
        "set_freeze",
        "watch-1",
        True,
        "100",
        250,
        Actor.USER,
    )
    assert (
        model.data(model.index(0, WatchColumn.NAME), Qt.ItemDataRole.BackgroundRole) == AMBER_TINT
    )

    fake.watch_values.emit({"watch-1": "73"})
    assert model.data(model.index(0, WatchColumn.VALUE)) == "73"
    qtbot.wait(1)


@pytest.mark.gui
def test_watch_view_freezes_unfreezes_and_removes_selected_rows(qtbot: QtBot) -> None:
    fake = FakeWatchController()
    view = WatchView(cast(AppController, fake))
    qtbot.addWidget(view)
    view.show()

    qtbot.mouseClick(view.freeze_all_button, Qt.MouseButton.LeftButton)
    assert fake.calls[-1] == (
        "set_freeze",
        "watch-1",
        True,
        "100",
        100,
        Actor.USER,
    )

    qtbot.mouseClick(view.unfreeze_all_button, Qt.MouseButton.LeftButton)
    assert fake.calls[-1] == (
        "set_freeze",
        "watch-1",
        False,
        "100",
        100,
        Actor.USER,
    )

    view.table.selectRow(0)
    assert view.create_trainer_button.isEnabled()
    with qtbot.waitSignal(view.trainer_create_requested, timeout=1000) as requested:
        qtbot.mouseClick(view.create_trainer_button, Qt.MouseButton.LeftButton)
    assert requested.args == ["watch-1"]

    assert view.remove_button.isEnabled()
    qtbot.mouseClick(view.remove_button, Qt.MouseButton.LeftButton)
    assert fake.calls[-1] == ("remove_watch", "watch-1", Actor.USER)
    assert view.model.rowCount() == 0


@pytest.mark.gui
def test_watch_view_workspace_buttons_use_controller_facade(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = FakeWatchController()
    view = WatchView(cast(AppController, fake))
    qtbot.addWidget(view)
    target = tmp_path / "sesion"
    source = tmp_path / "existente.json"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(target), t("watch.workspace.filter")),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(source), t("watch.workspace.filter")),
    )

    qtbot.mouseClick(view.save_workspace_button, Qt.MouseButton.LeftButton)
    assert fake.calls[-1] == (
        "save_workspace",
        target.with_suffix(".json"),
        Actor.USER,
    )
    qtbot.mouseClick(view.load_workspace_button, Qt.MouseButton.LeftButton)
    assert fake.calls[-1] == ("load_workspace", source, Actor.USER)


@pytest.mark.gui
def test_pointer_dialog_resolves_steps_reads_final_value_and_persists(qtbot: QtBot) -> None:
    fake = FakeWatchController()
    dialog = PointerDialog(cast(AppController, fake))
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.module_combo.count() == 1
    assert dialog.module_combo.currentData() == "memory_lab.exe"
    dialog.name_edit.setText("Jugador")
    dialog.base_offset_edit.setText("0x1000")

    dialog.offset_edit.setText("0x20")
    qtbot.mouseClick(dialog.add_offset_button, Qt.MouseButton.LeftButton)
    dialog.offset_edit.setText("0x8")
    qtbot.mouseClick(dialog.add_offset_button, Qt.MouseButton.LeftButton)
    assert [dialog.offsets_list.item(row).text() for row in range(2)] == [
        "0x20",
        "0x8",
    ]

    qtbot.mouseClick(dialog.resolve_button, Qt.MouseButton.LeftButton)
    assert dialog.steps_table.rowCount() == 2
    assert "0x0000000300000008" in dialog.final_address_label.text()
    assert dialog.final_value_label.text() == t("pointer.final.value", value="777")
    assert dialog.save_button.isEnabled()
    assert fake.calls[-2][0] == "resolve_chain"
    assert fake.calls[-1] == (
        "read_address",
        0x300000008,
        DataType.INT8,
    )

    with qtbot.waitSignal(dialog.watch_saved):
        qtbot.mouseClick(dialog.save_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert len(fake.added_specs) == 1
    saved = fake.added_specs[0]
    assert saved.label == "Jugador"
    assert saved.chain is not None
    assert saved.chain.module == "memory_lab.exe"
    assert saved.chain.base_offset == 0x1000
    assert saved.chain.offsets == [0x20, 0x8]
