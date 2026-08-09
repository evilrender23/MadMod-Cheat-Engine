"""Conversation and activity panel with a complete no-AI operating mode."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mempilot.i18n import t
from mempilot.ui.theme import SPACE_1, SPACE_2, SPACE_3


class ChatPanel(QWidget):
    """Render local conversation/activity state even when no provider is configured."""

    message_submitted = Signal(str)
    mode_changed = Signal(str)

    def __init__(self, ai_enabled: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatPanel")
        self.setMinimumWidth(320)
        self._ai_enabled = ai_enabled
        self._busy = False
        self._history: list[tuple[str, str]] = []
        self._activities: list[str] = []
        self._build_ui()
        self.set_ai_enabled(ai_enabled)

    @property
    def history(self) -> tuple[tuple[str, str], ...]:
        """Return an immutable snapshot for an orchestrator or persistence layer."""
        return tuple(self._history)

    @property
    def activities(self) -> tuple[str, ...]:
        return tuple(self._activities)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)
        heading_row = QHBoxLayout()
        heading = QLabel(t("chat.title"), self)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        heading_row.addWidget(QLabel(t("chat.mode"), self))
        self.mode_combo = QComboBox(self)
        self.mode_combo.setAccessibleName(t("chat.mode"))
        self.mode_combo.addItem(t("chat.mode.guided"), "guided")
        self.mode_combo.addItem(t("chat.mode.autonomous"), "autonomous")
        self.mode_combo.currentIndexChanged.connect(self._emit_mode)
        heading_row.addWidget(self.mode_combo)
        layout.addLayout(heading_row)
        self.autonomous_banner = QLabel("", self)
        self.autonomous_banner.setProperty("tone", "warning")
        self.autonomous_banner.setWordWrap(True)
        self.autonomous_banner.setVisible(False)
        layout.addWidget(self.autonomous_banner)
        self.writes_label = QLabel("", self)
        self.writes_label.setProperty("tone", "warning")
        self.writes_label.setVisible(False)
        layout.addWidget(self.writes_label)
        self.thinking_label = QLabel(t("chat.thinking"), self)
        self.thinking_label.setProperty("tone", "info")
        self.thinking_label.setVisible(False)
        layout.addWidget(self.thinking_label)
        self.trainer_button = QPushButton(t("chat.trainer_creator"), self)
        self.trainer_button.setAccessibleName(t("chat.trainer_creator"))
        self.trainer_button.clicked.connect(self._start_trainer_creator)
        layout.addWidget(self.trainer_button)

        self.disabled_card = QFrame(self)
        self.disabled_card.setProperty("card", True)
        disabled_layout = QVBoxLayout(self.disabled_card)
        disabled_layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        disabled_title = QLabel(t("agent.disabled"), self.disabled_card)
        title_font = disabled_title.font()
        title_font.setBold(True)
        disabled_title.setFont(title_font)
        disabled_title.setWordWrap(True)
        disabled_layout.addWidget(disabled_title)
        disabled_help = QLabel(t("chat.disabled_help"), self.disabled_card)
        disabled_help.setWordWrap(True)
        disabled_layout.addWidget(disabled_help)
        layout.addWidget(self.disabled_card)

        self.history_scroll = QScrollArea(self)
        self.history_scroll.setAccessibleName(t("chat.history_accessible"))
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.history_widget = QWidget(self.history_scroll)
        self.history_layout = QVBoxLayout(self.history_widget)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(SPACE_2)
        self.history_layout.addStretch(1)
        self.history_scroll.setWidget(self.history_widget)
        layout.addWidget(self.history_scroll, 1)
        activity_heading = QLabel(t("chat.activity"), self)
        activity_font = activity_heading.font()
        activity_font.setBold(True)
        activity_heading.setFont(activity_font)
        layout.addWidget(activity_heading)
        self.activity_container = QWidget(self)
        self.activity_layout = QVBoxLayout(self.activity_container)
        self.activity_layout.setContentsMargins(0, 0, 0, 0)
        self.activity_layout.setSpacing(SPACE_1)
        layout.addWidget(self.activity_container)

        input_row = QHBoxLayout()
        self.input_edit = QLineEdit(self)
        self.input_edit.setAccessibleName(t("chat.input"))
        self.input_edit.setPlaceholderText(t("chat.input"))
        self.input_edit.returnPressed.connect(self._submit)
        input_row.addWidget(self.input_edit, 1)
        self.send_button = QPushButton(t("chat.send"), self)
        self.send_button.setAccessibleName(t("chat.send"))
        self.send_button.setProperty("primary", True)
        self.send_button.clicked.connect(self._submit)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)
        QWidget.setTabOrder(self.mode_combo, self.trainer_button)
        QWidget.setTabOrder(self.trainer_button, self.input_edit)
        QWidget.setTabOrder(self.input_edit, self.send_button)

    def set_ai_enabled(self, enabled: bool) -> None:
        """Switch between configured and local no-provider behavior."""
        self._ai_enabled = enabled
        self.disabled_card.setVisible(not enabled)
        self.mode_combo.setEnabled(enabled)
        self.mode_combo.setToolTip("" if enabled else t("agent.disabled"))
        self.trainer_button.setEnabled(enabled and not self._busy)
        self.trainer_button.setToolTip("" if enabled else t("agent.disabled"))

    def set_busy(self, busy: bool) -> None:
        """Expose provider activity without blocking the rest of the application."""
        self._busy = busy
        self.thinking_label.setVisible(busy)
        enabled = self._ai_enabled and not busy
        self.input_edit.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        self.trainer_button.setEnabled(enabled)

    def set_mode(self, mode: str) -> None:
        """Synchronize the selector without recursively requesting a mode change."""
        index = self.mode_combo.findData(mode)
        if index < 0 or index == self.mode_combo.currentIndex():
            return
        blocked = self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(index)
        self.mode_combo.blockSignals(blocked)

    def add_user_message(self, text: str) -> None:
        self._append_message("user", t("chat.user"), text)

    def add_agent_message(self, text: str) -> None:
        self._append_message("agent", t("chat.agent"), text)

    def add_activity(self, text: str) -> None:
        """Append a compact typed-tool or controller activity row."""
        normalized = text.strip()
        if not normalized:
            return
        self._activities.append(normalized)
        label = QLabel(f"▸ {normalized}", self.activity_container)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setWordWrap(True)
        self.activity_layout.addWidget(label)

    def show_confirmation(
        self,
        detail: str,
        on_confirm: Callable[[], None],
        on_reject: Callable[[], None],
    ) -> QFrame:
        """Add an inline confirmation card for a future orchestrator."""
        card = QFrame(self.history_widget)
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        detail_label = QLabel(detail, card)
        detail_label.setWordWrap(True)
        detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(detail_label)
        buttons = QHBoxLayout()
        confirm = QPushButton(t("confirm.accept"), card)
        reject = QPushButton(t("confirm.reject"), card)
        confirm.setAccessibleName(t("confirm.accept"))
        reject.setAccessibleName(t("confirm.reject"))

        def finish(callback: Callable[[], None]) -> None:
            confirm.setEnabled(False)
            reject.setEnabled(False)
            callback()

        confirm.clicked.connect(lambda: finish(on_confirm))
        reject.clicked.connect(lambda: finish(on_reject))
        buttons.addWidget(confirm)
        buttons.addWidget(reject)
        card_layout.addLayout(buttons)
        self.history_layout.insertWidget(self.history_layout.count() - 1, card)
        self._scroll_to_bottom()
        return card

    def set_autonomous_state(
        self,
        active: bool,
        process_name: str = "",
        pid: int = 0,
        writes_used: int = 0,
        write_limit: int = 0,
    ) -> None:
        self.autonomous_banner.setText(
            t("agent.autonomous", name=process_name, pid=pid) if active else ""
        )
        self.autonomous_banner.setVisible(active)
        self.writes_label.setText(
            t("chat.writes", used=writes_used, limit=write_limit) if active else ""
        )
        self.writes_label.setVisible(active)

    @Slot()
    def _submit(self) -> None:
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        self.add_user_message(text)
        self.message_submitted.emit(text)
        if not self._ai_enabled:
            self.add_agent_message(t("chat.offline_reply"))

    @Slot()
    def _start_trainer_creator(self) -> None:
        if not self._ai_enabled or self._busy:
            return
        prompt = t("chat.trainer_prompt")
        self.add_user_message(prompt)
        self.message_submitted.emit(prompt)

    @Slot()
    def _emit_mode(self) -> None:
        mode = self.mode_combo.currentData()
        if isinstance(mode, str):
            self.mode_changed.emit(mode)

    def _append_message(self, actor: str, title: str, text: str) -> None:
        normalized = text.strip()
        if not normalized:
            return
        self._history.append((actor, normalized))
        card = QFrame(self.history_widget)
        card.setProperty("card", True)
        card.setObjectName(f"chatMessage_{actor}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(SPACE_2, SPACE_2, SPACE_2, SPACE_2)
        title_label = QLabel(title, card)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)
        card_layout.addWidget(title_label)
        body = QLabel(normalized, card)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(body)
        self.history_layout.insertWidget(self.history_layout.count() - 1, card)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        bar = self.history_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())


class AutonomousConsentDialog(QDialog):
    """Explicit, process-bound permission grant required before autonomous mode."""

    def __init__(
        self,
        process_name: str,
        pid: int,
        write_limit: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("chat.autonomous.title"))
        layout = QVBoxLayout(self)
        explanation = QLabel(
            t(
                "chat.autonomous.permissions",
                name=process_name,
                pid=pid,
                limit=write_limit,
            ),
            self,
        )
        explanation.setWordWrap(True)
        explanation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(explanation)
        self.consent = QCheckBox(t("chat.autonomous.consent"), self)
        self.consent.setAccessibleName(t("chat.autonomous.consent"))
        layout.addWidget(self.consent)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        accept = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        accept.setText(t("confirm.accept"))
        accept.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("confirm.reject"))
        self.consent.toggled.connect(accept.setEnabled)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
