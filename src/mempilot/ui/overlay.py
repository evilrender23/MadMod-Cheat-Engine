"""Compact topmost overlay for chat and guarded manual watch adjustments."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from html import escape

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCursor, QHideEvent, QKeyEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
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
from mempilot.services.trainer_service import TrainerTrickState
from mempilot.ui.theme import SPACE_2, SPACE_3, monospace_font


class OverlayWindow(QWidget):
    """Independent tool window shown only for the foreground attached process."""

    message_submitted = Signal(str)
    write_requested = Signal(str, str)
    freeze_requested = Signal(str, str, bool)
    trainer_toggle_requested = Signal(str, bool)
    trainer_values_save_requested = Signal(str, str, object)
    trainer_create_requested = Signal(str)

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
        self.setMinimumSize(440, 620)
        self.resize(500, 720)
        self._ai_enabled = False
        self._write_access = False
        self._identity: ProcessIdentity | None = None
        self._watches: dict[str, WatchEntry] = {}
        self._trainer_tricks: dict[str, TrainerTrickState] = {}
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
        trainers = QGroupBox(t("overlay.trainers"), card)
        trainer_layout = QVBoxLayout(trainers)
        self.trainer_combo = QComboBox(trainers)
        self.trainer_combo.setAccessibleName(t("overlay.trainer"))
        self.trainer_combo.currentIndexChanged.connect(self._trainer_selected)
        trainer_layout.addWidget(self.trainer_combo)
        self.trainer_info = QLabel("", trainers)
        self.trainer_info.setWordWrap(True)
        trainer_layout.addWidget(self.trainer_info)
        trainer_values_form = QFormLayout()
        self.trainer_enabled_edit = QLineEdit(trainers)
        self.trainer_enabled_edit.setFont(monospace_font())
        self.trainer_enabled_edit.setAccessibleName(t("overlay.trainer.enabled_value"))
        self.trainer_enabled_edit.textChanged.connect(self._update_trainer_buttons)
        trainer_values_form.addRow(t("overlay.trainer.enabled_value"), self.trainer_enabled_edit)
        self.trainer_disabled_edit = QLineEdit(trainers)
        self.trainer_disabled_edit.setFont(monospace_font())
        self.trainer_disabled_edit.setAccessibleName(t("overlay.trainer.disabled_value"))
        self.trainer_disabled_edit.textChanged.connect(self._update_trainer_buttons)
        trainer_values_form.addRow(t("overlay.trainer.disabled_value"), self.trainer_disabled_edit)
        self.trainer_disabled_label = trainer_values_form.labelForField(self.trainer_disabled_edit)
        trainer_layout.addLayout(trainer_values_form)
        self.trainer_edit_hint = QLabel("", trainers)
        self.trainer_edit_hint.setProperty("tone", "info")
        self.trainer_edit_hint.setWordWrap(True)
        trainer_layout.addWidget(self.trainer_edit_hint)
        self.trainer_save_values_button = QPushButton(t("overlay.trainer.save_values"), trainers)
        self.trainer_save_values_button.setAccessibleName(t("overlay.trainer.save_values"))
        self.trainer_save_values_button.clicked.connect(self._request_trainer_values_save)
        trainer_layout.addWidget(self.trainer_save_values_button)
        self.trainer_toggle_button = QPushButton(t("overlay.trainer.activate"), trainers)
        self.trainer_toggle_button.setAccessibleName(t("overlay.trainer.activate"))
        self.trainer_toggle_button.clicked.connect(self._request_trainer_toggle)
        trainer_layout.addWidget(self.trainer_toggle_button)
        layout.addWidget(trainers)

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
        self.create_trainer_button = QPushButton(t("overlay.trainer.create_manual"), manual)
        self.create_trainer_button.setAccessibleName(t("overlay.trainer.create_manual"))
        self.create_trainer_button.clicked.connect(self._request_manual_trainer)
        manual_layout.addWidget(self.create_trainer_button)
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
        self._trainer_selected()
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

    def refresh_trainer_tricks(self, states: Sequence[TrainerTrickState]) -> None:
        """Refresh the process-specific saved tricks without changing their runtime state."""
        selected = self.trainer_combo.currentData()
        self._trainer_tricks = {state.trick.id: state for state in states}
        blocked = self.trainer_combo.blockSignals(True)
        self.trainer_combo.clear()
        for state in states:
            marker = "●" if state.active else "○"
            self.trainer_combo.addItem(f"{marker} {state.trick.name}", state.trick.id)
        if isinstance(selected, str):
            index = self.trainer_combo.findData(selected)
            if index >= 0:
                self.trainer_combo.setCurrentIndex(index)
        self.trainer_combo.blockSignals(blocked)
        self._trainer_selected()

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
    def _trainer_selected(self) -> None:
        state = self._selected_trainer_trick()
        if state is None:
            process_name = self._identity.name if self._identity is not None else "—"
            self.trainer_info.setText(t("overlay.no_trainers", name=process_name))
            self.trainer_toggle_button.setText(t("overlay.trainer.activate"))
            self.trainer_toggle_button.setEnabled(False)
            self.trainer_enabled_edit.clear()
            self.trainer_disabled_edit.clear()
            self.trainer_disabled_edit.setVisible(False)
            if self.trainer_disabled_label is not None:
                self.trainer_disabled_label.setVisible(False)
            self._update_trainer_buttons()
            return
        trick = state.trick
        self.trainer_info.setText(
            t(
                "overlay.trainer_info",
                type=t(f"data_type.{trick.data_type.value}"),
                mode=t(f"overlay.trainer.mode.{trick.mode.value}"),
                state=t("overlay.trainer.active" if state.active else "overlay.trainer.inactive"),
            )
        )
        self.trainer_enabled_edit.setText(trick.enabled_value)
        self.trainer_disabled_edit.setText(trick.disabled_value or "")
        write_pair = trick.mode.value == "write_pair"
        self.trainer_disabled_edit.setVisible(write_pair)
        if self.trainer_disabled_label is not None:
            self.trainer_disabled_label.setVisible(write_pair)
        label = t("overlay.trainer.deactivate") if state.active else t("overlay.trainer.activate")
        self.trainer_toggle_button.setText(label)
        self.trainer_toggle_button.setAccessibleName(label)
        self.trainer_toggle_button.setEnabled(self._write_access)
        self._update_trainer_buttons()

    @Slot()
    def _update_trainer_buttons(self) -> None:
        state = self._selected_trainer_trick()
        editable = self._write_access and state is not None and not state.active
        self.trainer_enabled_edit.setEnabled(editable)
        self.trainer_disabled_edit.setEnabled(editable)
        requires_disabled = bool(state is not None and state.trick.mode.value == "write_pair")
        has_values = bool(self.trainer_enabled_edit.text().strip()) and (
            not requires_disabled or bool(self.trainer_disabled_edit.text().strip())
        )
        self.trainer_save_values_button.setEnabled(editable and has_values)
        self.trainer_edit_hint.setText(
            t("overlay.trainer.edit_inactive") if state is not None and state.active else ""
        )

    @Slot()
    def _update_manual_buttons(self) -> None:
        entry = self._selected_watch()
        has_value = bool(self.value_edit.text().strip())
        writable = self._write_access and entry is not None
        self.write_button.setEnabled(writable and has_value and not bool(entry and entry.frozen))
        self.freeze_button.setEnabled(writable and (bool(entry and entry.frozen) or has_value))
        self.create_trainer_button.setEnabled(writable)
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
    def _request_trainer_toggle(self) -> None:
        state = self._selected_trainer_trick()
        if state is not None and self._write_access:
            self.trainer_toggle_requested.emit(state.trick.id, not state.active)

    @Slot()
    def _request_trainer_values_save(self) -> None:
        state = self._selected_trainer_trick()
        if state is None or state.active or not self._write_access:
            return
        disabled: str | None = None
        if state.trick.mode.value == "write_pair":
            disabled = self.trainer_disabled_edit.text().strip()
        self.trainer_values_save_requested.emit(
            state.trick.id,
            self.trainer_enabled_edit.text().strip(),
            disabled,
        )

    @Slot()
    def _request_manual_trainer(self) -> None:
        entry = self._selected_watch()
        if entry is not None and self._write_access:
            self.trainer_create_requested.emit(entry.id)

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

    def _selected_trainer_trick(self) -> TrainerTrickState | None:
        trick_id = self.trainer_combo.currentData()
        return self._trainer_tricks.get(trick_id) if isinstance(trick_id, str) else None

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
