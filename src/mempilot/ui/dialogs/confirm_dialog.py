"""Explicit write confirmation dialog shared by manual and agent workflows."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mempilot.core.data_types import DataType, format_hex
from mempilot.i18n import t
from mempilot.ui.theme import SPACE_2, SPACE_3, monospace_font


class ConfirmDialog(QDialog):
    """Describe the exact memory mutation before the user authorizes it."""

    def __init__(
        self,
        *,
        action: str,
        address: int,
        data_type: DataType,
        current_value: str,
        new_value: str,
        allow_remember: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("confirm.title"))
        self.setModal(True)
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)
        heading = QLabel(t("confirm.title"), self)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSize(12)
        heading.setFont(heading_font)
        layout.addWidget(heading)
        form = QFormLayout()
        action_label = QLabel(action, self)
        action_label.setWordWrap(True)
        form.addRow(t("confirm.action"), action_label)
        address_label = QLabel(format_hex(address), self)
        address_label.setFont(monospace_font())
        address_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(t("confirm.address"), address_label)
        form.addRow(t("confirm.type"), QLabel(t(f"data_type.{data_type.value}"), self))
        change_label = QLabel(f"{current_value} → {new_value}", self)
        change_label.setFont(monospace_font())
        change_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        change_label.setWordWrap(True)
        form.addRow(t("confirm.change"), change_label)
        layout.addLayout(form)
        self.remember_check = QCheckBox(t("confirm.remember"), self)
        self.remember_check.setAccessibleName(t("confirm.remember"))
        self.remember_check.setVisible(allow_remember)
        layout.addWidget(self.remember_check)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        reject = QPushButton(t("confirm.reject"), self)
        reject.setAccessibleName(t("confirm.reject"))
        reject.clicked.connect(self.reject)
        confirm = QPushButton(t("confirm.accept"), self)
        confirm.setAccessibleName(t("confirm.accept"))
        confirm.setProperty("primary", True)
        confirm.setDefault(True)
        confirm.clicked.connect(self.accept)
        buttons.addWidget(reject)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)
        QWidget.setTabOrder(self.remember_check, reject)
        QWidget.setTabOrder(reject, confirm)

    @property
    def remember_for_session(self) -> bool:
        """Return the manual-only suppression choice after acceptance."""
        return self.remember_check.isVisible() and self.remember_check.isChecked()
