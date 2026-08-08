"""Fixed application and process controls displayed above the workspace."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from mempilot import __version__
from mempilot.core.backend import ProcessIdentity
from mempilot.i18n import t
from mempilot.ui.theme import SPACE_2, SPACE_3


class TopBar(QFrame):
    """Expose process lifecycle and global application actions."""

    attach_requested = Signal()
    detach_requested = Signal()
    memory_lab_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_2, SPACE_3, SPACE_2)
        layout.setSpacing(SPACE_2)

        name = QLabel(t("app.name"), self)
        name_font = name.font()
        name_font.setBold(True)
        name_font.setPointSize(11)
        name.setFont(name_font)
        layout.addWidget(name)
        layout.addWidget(QLabel(t("app.version", version=__version__), self))

        self.attach_button = QPushButton(t("action.attach"), self)
        self.attach_button.setAccessibleName(t("action.attach"))
        self.attach_button.clicked.connect(self.attach_requested)
        layout.addWidget(self.attach_button)

        self.process_label = QLabel(t("top.disconnected_summary"), self)
        self.process_label.setAccessibleName(t("top.process_accessible"))
        self.process_label.setTextInteractionFlags(self.process_label.textInteractionFlags())
        layout.addWidget(self.process_label, 1)

        self.connection_label = QLabel(self._connection_text("●", t("status.disconnected")), self)
        self.connection_label.setProperty("tone", "error")
        self.connection_label.setAccessibleName(
            t("top.connection_accessible", state=t("status.disconnected"))
        )
        layout.addWidget(self.connection_label)

        self.access_label = QLabel(t("status.read_only"), self)
        self.access_label.setVisible(False)
        layout.addWidget(self.access_label)

        self.detach_button = QPushButton(t("action.detach"), self)
        self.detach_button.setAccessibleName(t("action.detach"))
        self.detach_button.setEnabled(False)
        self.detach_button.clicked.connect(self.detach_requested)
        layout.addWidget(self.detach_button)

        self.memory_lab_button = QPushButton(t("action.memory_lab"), self)
        self.memory_lab_button.setAccessibleName(t("action.memory_lab"))
        self.memory_lab_button.clicked.connect(self.memory_lab_requested)
        layout.addWidget(self.memory_lab_button)

        self.settings_button = QPushButton(t("action.settings"), self)
        self.settings_button.setAccessibleName(t("action.settings"))
        self.settings_button.clicked.connect(self.settings_requested)
        layout.addWidget(self.settings_button)

        QWidget.setTabOrder(self.attach_button, self.detach_button)
        QWidget.setTabOrder(self.detach_button, self.memory_lab_button)
        QWidget.setTabOrder(self.memory_lab_button, self.settings_button)

    def set_attached(self, identity: ProcessIdentity, write_access: bool) -> None:
        """Render a complete non-color-only attached status."""
        self.process_label.setText(
            t(
                "top.process_summary",
                pid=identity.pid,
                name=identity.name,
                arch=identity.architecture.value,
            )
        )
        state = t("status.connected")
        self.connection_label.setText(self._connection_text("●", state))
        self.connection_label.setProperty("tone", "success" if write_access else "warning")
        self.connection_label.setAccessibleName(t("top.connection_accessible", state=state))
        self.connection_label.style().unpolish(self.connection_label)
        self.connection_label.style().polish(self.connection_label)
        self.access_label.setText(t("status.read_write") if write_access else t("status.read_only"))
        self.access_label.setProperty("tone", "warning" if not write_access else "success")
        self.access_label.setVisible(True)
        self.detach_button.setEnabled(True)

    def set_detached(self) -> None:
        """Return the controls to their disconnected state."""
        self.process_label.setText(t("top.disconnected_summary"))
        state = t("status.disconnected")
        self.connection_label.setText(self._connection_text("●", state))
        self.connection_label.setProperty("tone", "error")
        self.connection_label.setAccessibleName(t("top.connection_accessible", state=state))
        self.connection_label.style().unpolish(self.connection_label)
        self.connection_label.style().polish(self.connection_label)
        self.access_label.setVisible(False)
        self.detach_button.setEnabled(False)

    @staticmethod
    def _connection_text(symbol: str, state: str) -> str:
        return f"{symbol} {state}"
