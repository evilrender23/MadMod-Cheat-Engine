"""Actionable error dialog with opt-in technical details."""

from __future__ import annotations

import traceback

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mempilot.core.exceptions import MemPilotError
from mempilot.i18n import t
from mempilot.ui.theme import SPACE_2, SPACE_3


class ErrorDialog(QDialog):
    """Show safe recovery guidance first and technical context on demand."""

    def __init__(self, exc: BaseException, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("error.title"))
        self.setModal(True)
        self.setMinimumWidth(560)
        user_message = exc.user_message() if isinstance(exc, MemPilotError) else t("error.unknown")
        self._details = "".join(traceback.format_exception(exc)).strip()
        if not self._details:
            self._details = f"{type(exc).__name__}: {exc}"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)
        heading = QLabel(t("error.title"), self)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSize(12)
        heading.setFont(heading_font)
        heading.setProperty("tone", "error")
        layout.addWidget(heading)
        message = QLabel(user_message, self)
        message.setWordWrap(True)
        message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(message)
        self.details_toggle = QToolButton(self)
        self.details_toggle.setText(t("error.details"))
        self.details_toggle.setAccessibleName(t("error.details"))
        self.details_toggle.setCheckable(True)
        self.details_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.details_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.details_toggle.toggled.connect(self._toggle_details)
        layout.addWidget(self.details_toggle)
        self.details_edit = QPlainTextEdit(self._details, self)
        self.details_edit.setAccessibleName(t("error.technical"))
        self.details_edit.setReadOnly(True)
        self.details_edit.setMinimumHeight(160)
        self.details_edit.setVisible(False)
        layout.addWidget(self.details_edit)
        buttons = QHBoxLayout()
        self.copy_button = QPushButton(t("error.copy"), self)
        self.copy_button.setAccessibleName(t("error.copy"))
        self.copy_button.clicked.connect(self._copy)
        close = QPushButton(t("ui.close"), self)
        close.setAccessibleName(t("ui.close"))
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        QWidget.setTabOrder(self.details_toggle, self.copy_button)
        QWidget.setTabOrder(self.copy_button, close)

    @Slot(bool)
    def _toggle_details(self, visible: bool) -> None:
        self.details_edit.setVisible(visible)
        self.details_toggle.setArrowType(
            Qt.ArrowType.DownArrow if visible else Qt.ArrowType.RightArrow
        )
        self.adjustSize()

    @Slot()
    def _copy(self) -> None:
        QApplication.clipboard().setText(self._details)
