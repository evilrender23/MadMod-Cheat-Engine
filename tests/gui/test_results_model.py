"""Regression contracts for bounded live-result refreshes."""

from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtCore import QModelIndex, QObject, Signal
from pytestqt.qtbot import QtBot

from mempilot.controller import ResultsPage
from mempilot.core.data_types import DataType
from mempilot.core.scan_session import CandidateRow
from mempilot.ui.models.results_model import ResultsModel

pytestmark = pytest.mark.gui


class _Controller(QObject):
    """Minimal results facade used to observe the model's refresh signals."""

    result_values = Signal(object)

    def __init__(self, rows: list[CandidateRow]) -> None:
        super().__init__()
        self.rows = rows
        self.visible: list[CandidateRow] = []

    def results_page(self, offset: int, limit: int, _order: Any, _filter: Any) -> ResultsPage:
        page = self.rows[offset : offset + limit]
        return ResultsPage(page, offset, limit, len(self.rows), len(self.rows))

    def set_visible_results(self, rows: list[CandidateRow]) -> None:
        self.visible = list(rows)


def _row(index: int) -> CandidateRow:
    return CandidateRow(
        address=0x1000 + index * 4,
        current="100",
        previous="",
        data_type=DataType.INT32,
        region="laboratorio",
        protection="RW",
        change_rate=0.0,
        readable=True,
        writable=True,
    )


def test_live_refresh_skips_unchanged_rows_and_batches_changes(qtbot: QtBot) -> None:
    controller = _Controller([_row(index) for index in range(1000)])
    model = ResultsModel(controller, page_size=1000)  # type: ignore[arg-type]
    model.reload()
    changes: list[tuple[int, int]] = []

    def record_change(top_left: QModelIndex, bottom_right: QModelIndex, _roles: list[int]) -> None:
        changes.append((top_left.row(), bottom_right.row()))

    model.dataChanged.connect(record_change)
    unchanged = {row.address: "100" for row in controller.rows}
    controller.result_values.emit(unchanged)
    qtbot.wait(1)
    assert changes == []

    updated = {row.address: "101" for row in controller.rows}
    controller.result_values.emit(updated)
    qtbot.wait(1)
    assert changes == [(0, 999)]
    assert all(row.current == "101" for row in model.rows)
