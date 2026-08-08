"""Context, scan progress, metrics, and cancellation controls."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from mempilot.core.scanner import ScanProgress
from mempilot.i18n import t
from mempilot.ui.theme import SPACE_2, SPACE_3


class StatusBar(QWidget):
    """Dense status strip that never communicates scan state by color alone."""

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_2, SPACE_3, SPACE_2)
        layout.setSpacing(SPACE_2)
        self.message_label = QLabel(t("status.ready"), self)
        self.message_label.setMinimumWidth(220)
        layout.addWidget(self.message_label, 1)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setAccessibleName(t("status.progress_accessible"))
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar, 1)
        self.metrics_label = QLabel("", self)
        self.metrics_label.setVisible(False)
        layout.addWidget(self.metrics_label)
        self.cancel_button = QPushButton(t("action.cancel"), self)
        self.cancel_button.setAccessibleName(t("action.cancel"))
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.cancel_button.setVisible(False)
        layout.addWidget(self.cancel_button)

    def set_message(self, message: str, tone: str | None = None) -> None:
        """Set contextual text and an optional semantic tone."""
        self.message_label.setText(message)
        self.message_label.setProperty("tone", tone or "")
        self.message_label.style().unpolish(self.message_label)
        self.message_label.style().polish(self.message_label)

    def start_scan(self) -> None:
        self.set_message(t("status.scanning"))
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.metrics_label.setVisible(True)
        self.cancel_button.setVisible(True)

    def update_progress(self, progress: ScanProgress) -> None:
        """Update bounded progress and all required throughput counters."""
        self.progress_bar.setRange(0, 1000)
        fraction = progress.bytes_done / progress.bytes_total if progress.bytes_total else 0.0
        self.progress_bar.setValue(max(0, min(1000, round(fraction * 1000))))
        self.metrics_label.setText(
            t(
                "status.metrics",
                done=progress.regions_done,
                total=progress.regions_total,
                megabytes=f"{progress.bytes_done / (1 << 20):.0f}",
                speed=f"{progress.bytes_per_s / (1 << 20):.0f}",
                elapsed=f"{progress.elapsed_s:.1f}",
            )
        )

    def finish_scan(self, message: str, tone: str | None = None) -> None:
        self.progress_bar.setVisible(False)
        self.metrics_label.setVisible(False)
        self.cancel_button.setVisible(False)
        self.set_message(message, tone)

    def reset(self) -> None:
        self.progress_bar.setVisible(False)
        self.metrics_label.setVisible(False)
        self.cancel_button.setVisible(False)
        self.set_message(t("status.ready"))
