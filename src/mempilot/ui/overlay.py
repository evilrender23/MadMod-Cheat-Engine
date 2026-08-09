"""Compact topmost overlay for chat and guarded manual watch adjustments."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from html import escape

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCursor, QHideEvent, QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mempilot.core.backend import ProcessIdentity
from mempilot.core.watcher import WatchEntry
from mempilot.i18n import t
from mempilot.ui.theme import SPACE_2, SPACE_3, monospace_font


class OverlayWindow(QWidget):
    """Independent tool window shown only for the foreground attached process."""

    message_submitted = Signal(str)
    write_requested = Signal(str, str)
    freeze_requested = Signal(str, str, bool)

    def __init__(self) -> None:
        super().__init__(None)
        self.setObjectName("mempilotOverlay")
        self.setWindowTitle(t("overlay.title"))
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowOpacity(0.97)
        self.setMinimumSize(440, 540)
        self.resize(500, 640)
        self._ai_enabled = False
        self._write_access = False
        self._identity: ProcessIdentity | None = None
        self._watches: dict[str, WatchEntry] = {}
        self._pending_confirmation: tuple[Callable[[], None], Callable[[], None]] | None = None
        self._build_ui()

    @property
    def bound_identity(self) -> ProcessIdentity | None:
        """Return the exact process instance represented by the overlay."""
        return self._identity

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE_2, SPACE_2, SPACE_2, SPACE_2)
        card = QFrame(self)
        card.setObjectName("overlayCard")
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)

        header = QHBoxLayout()
        title = QLabel(t("overlay.title"), card)
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch(1)
        hide_button = QPushButton(t("overlay.hide"), card)
        hide_button.setAccessibleName(t("overlay.hide"))
        hide_button.clicked.connect(self.hide)
        header.addWidget(hide_button)
        layout.addLayout(header)
        self.process_label = QLabel(t("overlay.no_process"), card)
        self.process_label.setProperty("tone", "info")
        self.process_label.setWordWrap(True)
        layout.addWidget(self.process_label)
        hint = QLabel(t("overlay.hotkey_hint"), card)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.history = QTextBrowser(card)
        self.history.setObjectName("overlayHistory")
        self.history.setAccessibleName(t("overlay.history"))
        self.history.setOpenExternalLinks(False)
        self.history.document().setMaximumBlockCount(120)
        layout.addWidget(self.history, 1)
        self.activity_label = QLabel("", card)
        self.activity_label.setWordWrap(True)
        self.activity_label.setProperty("tone", "info")
        layout.addWidget(self.activity_label)

        chat_row = QHBoxLayout()
        self.chat_input = QLineEdit(card)
        self.chat_input.setAccessibleName(t("overlay.chat_input"))
        self.chat_input.setPlaceholderText(t("overlay.chat_input"))
        self.chat_input.returnPressed.connect(self._submit_chat)
        chat_row.addWidget(self.chat_input, 1)
        self.send_button = QPushButton(t("chat.send"), card)
        self.send_button.setAccessibleName(t("chat.send"))
        self.send_button.setProperty("primary", True)
        self.send_button.clicked.connect(self._submit_chat)
        chat_row.addWidget(self.send_button)
        layout.addLayout(chat_row)

        self.confirmation_card = QFrame(card)
        self.confirmation_card.setProperty("card", True)
        confirmation_layout = QVBoxLayout(self.confirmation_card)
        self.confirmation_detail = QLabel("", self.confirmation_card)
        self.confirmation_detail.setWordWrap(True)
        confirmation_layout.addWidget(self.confirmation_detail)
        confirmation_actions = QHBoxLayout()
        self.confirm_button = QPushButton(t("confirm.accept"), self.confirmation_card)
        self.reject_button = QPushButton(t("confirm.reject"), self.confirmation_card)
        self.confirm_button.clicked.connect(self._confirm_pending)
        self.reject_button.clicked.connect(self._reject_pending)
        confirmation_actions.addWidget(self.confirm_button)
        confirmation_actions.addWidget(self.reject_button)
        confirmation_layout.addLayout(confirmation_actions)
        self.confirmation_card.setVisible(False)
        layout.addWidget(self.confirmation_card)

        manual = QGroupBox(t("overlay.manual"), card)
        manual_layout = QVBoxLayout(manual)
        self.watch_combo = QComboBox(manual)
        self.watch_combo.setAccessibleName(t("overlay.watch"))
        self.watch_combo.currentIndexChanged.connect(self._watch_selected)
        manual_layout.addWidget(self.watch_combo)
        self.watch_info = QLabel(t("overlay.no_watches"), manual)
        self.watch_info.setWordWrap(True)
        manual_layout.addWidget(self.watch_info)
        self.value_edit = QLineEdit(manual)
        self.value_edit.setAccessibleName(t("overlay.value"))
        self.value_edit.setPlaceholderText(t("overlay.value"))
        self.value_edit.setFont(monospace_font())
        self.value_edit.textChanged.connect(self._update_manual_buttons)
        manual_layout.addWidget(self.value_edit)
        manual_actions = QHBoxLayout()
        self.write_button = QPushButton(t("overlay.write"), manual)
        self.write_button.setAccessibleName(t("overlay.write"))
        self.write_button.clicked.connect(self._request_write)
        self.freeze_button = QPushButton(t("overlay.freeze"), manual)
        self.freeze_button.setAccessibleName(t("overlay.freeze"))
        self.freeze_button.clicked.connect(self._request_freeze)
        manual_actions.addWidget(self.write_button)
        manual_actions.addWidget(self.freeze_button)
        manual_layout.addLayout(manual_actions)
        self.operation_status = QLabel("", manual)
        self.operation_status.setWordWrap(True)
        manual_layout.addWidget(self.operation_status)
        layout.addWidget(manual)
        outer.addWidget(card)
        self._update_manual_buttons()

    def show_for_process(
        self,
        identity: ProcessIdentity,
        write_access: bool,
        watches: Sequence[WatchEntry],
    ) -> None:
        """Refresh process-bound state and show near the active screen's top-right corner."""
        self._identity = identity
        self._write_access = write_access
        self.process_label.setText(
            t(
                "overlay.process",
                name=identity.name,
                pid=identity.pid,
                access=t("status.read_write") if write_access else t("status.read_only"),
            )
        )
        self.refresh_watches(watches)
        screen = self.screen()
        cursor_screen = self.screen().virtualSiblingAt(QCursor.pos())
        if cursor_screen is not None:
            screen = cursor_screen
        bounds = screen.availableGeometry()
        self.move(bounds.right() - self.width() - 24, bounds.top() + 24)
        self.show()
        self.raise_()
        self.activateWindow()
        self.chat_input.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def set_ai_enabled(self, enabled: bool) -> None:
        self._ai_enabled = enabled
        self.send_button.setEnabled(enabled)
        self.chat_input.setEnabled(enabled)
        self.chat_input.setToolTip("" if enabled else t("agent.disabled"))

    def set_busy(self, busy: bool) -> None:
        self.send_button.setEnabled(self._ai_enabled and not busy)
        self.chat_input.setEnabled(self._ai_enabled and not busy)
        self.activity_label.setText(t("chat.thinking") if busy else "")

    def set_history(self, messages: Sequence[tuple[str, str]]) -> None:
        self.history.clear()
        for role, text in messages:
            self._append_message(role, text)

    def add_user_message(self, text: str) -> None:
        self._append_message("user", text)

    def add_agent_message(self, text: str) -> None:
        self._append_message("assistant", text)

    def add_activity(self, text: str) -> None:
        normalized = text.strip()
        if normalized:
            self.activity_label.setText(f"▸ {normalized}")

    def show_confirmation(
        self,
        detail: str,
        on_confirm: Callable[[], None],
        on_reject: Callable[[], None],
    ) -> None:
        if self._pending_confirmation is not None:
            self._reject_pending()
        self._pending_confirmation = (on_confirm, on_reject)
        self.confirmation_detail.setText(detail)
        self.confirmation_card.setVisible(True)

    def refresh_watches(self, watches: Sequence[WatchEntry]) -> None:
        selected = self.watch_combo.currentData()
        self._watches = {entry.id: entry for entry in watches}
        blocked = self.watch_combo.blockSignals(True)
        self.watch_combo.clear()
        for entry in watches:
            value = entry.current_value or "—"
            self.watch_combo.addItem(f"{entry.label} · {value}", entry.id)
        if isinstance(selected, str):
            index = self.watch_combo.findData(selected)
            if index >= 0:
                self.watch_combo.setCurrentIndex(index)
        self.watch_combo.blockSignals(blocked)
        self._watch_selected()

    def set_operation_result(self, message: str, *, error: bool = False) -> None:
        self.operation_status.setText(message)
        self.operation_status.setProperty("tone", "error" if error else "success")
        self.operation_status.style().unpolish(self.operation_status)
        self.operation_status.style().polish(self.operation_status)

    @Slot()
    def _submit_chat(self) -> None:
        text = self.chat_input.text().strip()
        if not text or not self._ai_enabled:
            return
        self.chat_input.clear()
        self.add_user_message(text)
        self.message_submitted.emit(text)

    @Slot()
    def _watch_selected(self) -> None:
        entry = self._selected_watch()
        if entry is None:
            self.watch_info.setText(t("overlay.no_watches"))
            self.value_edit.clear()
        else:
            self.watch_info.setText(
                t(
                    "overlay.watch_info",
                    type=t(f"data_type.{entry.data_type.value}"),
                    current=entry.current_value or "—",
                    frozen=t("overlay.yes") if entry.frozen else t("overlay.no"),
                )
            )
            self.value_edit.setText(entry.desired_value or entry.current_value)
            self.freeze_button.setText(
                t("overlay.unfreeze") if entry.frozen else t("overlay.freeze")
            )
        self._update_manual_buttons()

    @Slot()
    def _update_manual_buttons(self) -> None:
        entry = self._selected_watch()
        has_value = bool(self.value_edit.text().strip())
        writable = self._write_access and entry is not None
        self.write_button.setEnabled(writable and has_value and not bool(entry and entry.frozen))
        self.freeze_button.setEnabled(writable and (bool(entry and entry.frozen) or has_value))
        if entry is not None and not self._write_access:
            self.operation_status.setText(t("overlay.read_only"))

    @Slot()
    def _request_write(self) -> None:
        entry = self._selected_watch()
        value = self.value_edit.text().strip()
        if entry is not None and value:
            self.write_requested.emit(entry.id, value)

    @Slot()
    def _request_freeze(self) -> None:
        entry = self._selected_watch()
        if entry is None:
            return
        value = self.value_edit.text().strip()
        self.freeze_requested.emit(entry.id, value, not entry.frozen)

    @Slot()
    def _confirm_pending(self) -> None:
        if self._pending_confirmation is None:
            return
        confirm, _reject = self._pending_confirmation
        self._pending_confirmation = None
        self.confirmation_card.setVisible(False)
        confirm()

    @Slot()
    def _reject_pending(self) -> None:
        if self._pending_confirmation is None:
            return
        _confirm, reject = self._pending_confirmation
        self._pending_confirmation = None
        self.confirmation_card.setVisible(False)
        reject()

    def _selected_watch(self) -> WatchEntry | None:
        watch_id = self.watch_combo.currentData()
        return self._watches.get(watch_id) if isinstance(watch_id, str) else None

    def _append_message(self, role: str, text: str) -> None:
        normalized = text.strip()
        if not normalized:
            return
        title = t("chat.user") if role == "user" else t("chat.agent")
        self.history.append(f"<b>{escape(title)}</b><br>{escape(normalized)}")
        bar = self.history.verticalScrollBar()
        bar.setValue(bar.maximum())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        if self._pending_confirmation is not None:
            self._reject_pending()
        super().hideEvent(event)
