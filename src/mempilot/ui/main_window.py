"""Main M@D-Engine window and complete GUI-to-controller wiring."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, Qt, Slot
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mempilot.agent.orchestrator import (
    AgentOrchestrator,
    ConfirmationRequest,
)
from mempilot.agent.policies import AgentMode
from mempilot.agent.providers import create_cli_provider
from mempilot.branding import APP_NAME, ORGANIZATION_NAME
from mempilot.config.settings import Settings
from mempilot.controller import Actor, AppController
from mempilot.core.data_types import DataType, format_hex
from mempilot.core.exceptions import MemPilotError
from mempilot.core.scan_session import CandidateRow, ScanSession, SessionState
from mempilot.core.scanner import ScanProgress, ScanRequest
from mempilot.core.watcher import WatchEntry, WatchSpec
from mempilot.i18n import t
from mempilot.services.settings_service import SettingsService
from mempilot.services.trainer_service import TrainerTrickState, TrickMode
from mempilot.ui.dialogs.attach_dialog import AttachDialog
from mempilot.ui.dialogs.confirm_dialog import ConfirmDialog
from mempilot.ui.dialogs.error_dialog import ErrorDialog
from mempilot.ui.dialogs.settings_dialog import SettingsDialog
from mempilot.ui.dialogs.trainer_dialog import TrainerDialog
from mempilot.ui.hotkeys import GlobalHotkeys, HotkeyEventFilter
from mempilot.ui.overlay import OverlayWindow
from mempilot.ui.widgets.chat_panel import AutonomousConsentDialog, ChatPanel
from mempilot.ui.widgets.results_view import ResultsView
from mempilot.ui.widgets.scan_panel import ScanPanel
from mempilot.ui.widgets.status_bar import StatusBar
from mempilot.ui.widgets.top_bar import TopBar
from mempilot.ui.widgets.watch_view import WatchView


class MainWindow(QMainWindow):
    """Dense, persistent application shell driven only by AppController."""

    def __init__(
        self,
        controller: AppController,
        settings: Settings | None = None,
        settings_service: SettingsService | None = None,
        parent: QWidget | None = None,
        *,
        orchestrator: AgentOrchestrator | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.settings = settings or Settings()
        self.settings_service = settings_service or SettingsService()
        self.orchestrator = orchestrator
        self._layout_settings = QSettings(ORGANIZATION_NAME, APP_NAME)
        self._write_confirmation_enabled = True
        self._last_write_access = False
        self.overlay = OverlayWindow()
        self._hotkeys = GlobalHotkeys()
        self._hotkeys_registered = False
        self._hotkey_filter = HotkeyEventFilter(self._hotkeys, self.toggle_overlay)
        self._native_hotkeys_enabled = (
            sys.platform == "win32" and QApplication.platformName() == "windows"
        )
        application = QApplication.instance()
        if application is not None and self._native_hotkeys_enabled:
            application.installNativeEventFilter(self._hotkey_filter)
        self.setWindowTitle(t("app.name"))
        self.setMinimumSize(1280, 720)
        self.resize(1760, 1000)
        self._build_ui()
        self._connect_controller()
        self._install_global_actions()
        self._restore_layout()
        self._apply_initial_state()

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.top_bar = TopBar(central)
        layout.addWidget(self.top_bar)

        self.scan_panel = ScanPanel(self.settings, central)
        self.results_view = ResultsView(
            self.controller, self.settings.ui.results_page_size, central
        )
        self.chat_panel = ChatPanel(
            ai_enabled=self.orchestrator is not None and self.orchestrator.available,
            parent=central,
        )
        self.horizontal_splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self.horizontal_splitter.addWidget(self.scan_panel)
        self.horizontal_splitter.addWidget(self.results_view)
        self.horizontal_splitter.addWidget(self.chat_panel)
        self.horizontal_splitter.setStretchFactor(0, 0)
        self.horizontal_splitter.setStretchFactor(1, 1)
        self.horizontal_splitter.setStretchFactor(2, 0)
        self.horizontal_splitter.setCollapsible(0, False)
        self.horizontal_splitter.setCollapsible(1, False)
        self.horizontal_splitter.setCollapsible(2, True)
        self.horizontal_splitter.setSizes([320, 1060, 380])

        self.watch_view = WatchView(self.controller, central)
        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical, central)
        self.vertical_splitter.addWidget(self.horizontal_splitter)
        self.vertical_splitter.addWidget(self.watch_view)
        self.vertical_splitter.setStretchFactor(0, 1)
        self.vertical_splitter.setStretchFactor(1, 0)
        self.vertical_splitter.setCollapsible(0, False)
        self.vertical_splitter.setCollapsible(1, False)
        self.vertical_splitter.setSizes([780, 220])
        layout.addWidget(self.vertical_splitter, 1)

        self.status_strip = StatusBar(central)
        layout.addWidget(self.status_strip)
        self.setCentralWidget(central)
        self._connect_widgets()

    def _connect_widgets(self) -> None:
        self.top_bar.attach_requested.connect(self.select_process)
        self.top_bar.detach_requested.connect(self.detach_process)
        self.top_bar.memory_lab_requested.connect(self.launch_memory_lab)
        self.top_bar.settings_requested.connect(self.open_settings)
        self.scan_panel.first_scan_requested.connect(self.start_first_scan)
        self.scan_panel.next_scan_requested.connect(self.start_next_scan)
        self.scan_panel.reset_requested.connect(self.reset_scan)
        self.scan_panel.cancel_requested.connect(self.controller.cancel_scan)
        self.status_strip.cancel_requested.connect(self.controller.cancel_scan)
        self.results_view.add_watch_requested.connect(self.add_result_watch)
        self.results_view.edit_value_requested.connect(self.edit_result_value)
        self.results_view.reinterpret_requested.connect(self.reinterpret_result)
        self.results_view.error_raised.connect(self.show_error)
        self.watch_view.workspace_saved.connect(self._workspace_saved)
        self.watch_view.workspace_loaded.connect(self._workspace_loaded)
        self.watch_view.trainer_create_requested.connect(self._create_manual_trainer)
        self.overlay.message_submitted.connect(self._submit_overlay_message)
        self.overlay.write_requested.connect(self._overlay_write_watch)
        self.overlay.freeze_requested.connect(self._overlay_set_freeze)
        self.overlay.trainer_toggle_requested.connect(self._overlay_toggle_trick)
        self.overlay.trainer_values_save_requested.connect(self._overlay_save_trainer_values)
        self.overlay.trainer_create_requested.connect(self._create_manual_trainer)
        if self.orchestrator is not None:
            self.chat_panel.message_submitted.connect(self._submit_agent_message)
            self.chat_panel.message_submitted.connect(self._mirror_main_user_in_overlay)
            self.chat_panel.mode_changed.connect(self._request_agent_mode)
            self.orchestrator.response_ready.connect(self.chat_panel.add_agent_message)
            self.orchestrator.response_ready.connect(self.overlay.add_agent_message)
            self.orchestrator.activity.connect(self.chat_panel.add_activity)
            self.orchestrator.activity.connect(self.overlay.add_activity)
            self.orchestrator.confirmation_requested.connect(self._show_agent_confirmation)
            self.orchestrator.busy_changed.connect(self.chat_panel.set_busy)
            self.orchestrator.busy_changed.connect(self.overlay.set_busy)
            self.orchestrator.mode_changed.connect(self.chat_panel.set_mode)

    def _connect_controller(self) -> None:
        self.controller.attached.connect(self._on_attached)
        self.controller.detached.connect(self._on_detached)
        self.controller.process_lost.connect(self._on_process_lost)
        self.controller.scan_started.connect(self._on_scan_started)
        self.controller.scan_progress.connect(self._on_scan_progress)
        self.controller.scan_finished.connect(self._on_scan_finished)
        self.controller.scan_failed.connect(self._on_scan_failed)
        self.controller.scan_cancelled.connect(self._on_scan_cancelled)
        self.controller.watch_write_error.connect(self._on_watch_error)
        self.controller.autonomous_changed.connect(self._on_autonomous_changed)
        self.controller.watches_changed.connect(self._refresh_overlay_watches)
        self.controller.trainers_changed.connect(self._refresh_overlay_trainers)

    def _install_global_actions(self) -> None:
        specs = (
            ("first_scan", t("action.first_scan"), "F5", self.scan_panel.first_button.click),
            ("next_scan", t("action.next_scan"), "F6", self.scan_panel.next_button.click),
            ("cancel_scan", t("action.cancel"), "Esc", self.scan_panel.cancel_button.click),
            ("reset_scan", t("action.reset"), "Ctrl+R", self.scan_panel.reset_button.click),
            ("attach", t("action.attach"), "Ctrl+P", self.select_process),
            ("save", t("action.save_workspace"), "Ctrl+S", self.save_workspace),
            ("load", t("action.load_workspace"), "Ctrl+O", self.load_workspace),
            ("lab", t("action.memory_lab"), "Ctrl+L", self.launch_memory_lab),
            ("help", t("help.title"), "F1", self.show_help),
        )
        self.global_actions: dict[str, QAction] = {}
        for name, label, sequence, callback in specs:
            action = QAction(label, self)
            action.setStatusTip(label)
            action.setToolTip(f"{label} ({sequence})")
            action.setShortcut(QKeySequence(sequence))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(callback)
            self.addAction(action)
            self.global_actions[name] = action

    def _apply_initial_state(self) -> None:
        identity = self.controller.attached_identity()
        attached = identity is not None
        if identity is not None:
            self.top_bar.set_attached(identity, self._last_write_access)
        self.scan_panel.set_session_state(self.controller.scan_status().state, attached)

    @Slot(str)
    def _submit_agent_message(self, text: str) -> None:
        if self.orchestrator is None:
            return
        try:
            self.orchestrator.submit(text)
        except Exception as exc:
            self.show_error(exc)

    @Slot(str)
    def _submit_overlay_message(self, text: str) -> None:
        self.chat_panel.add_user_message(text)
        self._submit_agent_message(text)

    @Slot(str)
    def _mirror_main_user_in_overlay(self, text: str) -> None:
        if self.overlay.isVisible():
            self.overlay.add_user_message(text)

    @Slot(str)
    def _request_agent_mode(self, raw_mode: str) -> None:
        if self.orchestrator is None:
            return
        if raw_mode == AgentMode.GUIDED.value:
            self.orchestrator.set_guided_mode()
            return
        if raw_mode != AgentMode.AUTONOMOUS.value:
            self.chat_panel.set_mode(self.orchestrator.policy.mode.value)
            return
        identity = self.controller.attached_identity()
        if identity is None:
            QMessageBox.information(
                self,
                t("chat.autonomous.title"),
                t("chat.autonomous.needs_process"),
            )
            self.chat_panel.set_mode(AgentMode.GUIDED.value)
            return
        consent = AutonomousConsentDialog(
            identity.name,
            identity.pid,
            self.orchestrator.policy.write_limit,
            self,
        )
        if (
            consent.exec() != QDialog.DialogCode.Accepted
            or not self.orchestrator.activate_autonomous_mode()
        ):
            self.chat_panel.set_mode(AgentMode.GUIDED.value)

    @Slot(object)
    def _show_agent_confirmation(self, raw_request: object) -> None:
        if not isinstance(raw_request, ConfirmationRequest):
            return
        if self.overlay.isVisible():
            self.overlay.show_confirmation(
                raw_request.detail,
                raw_request.confirm,
                raw_request.reject,
            )
        else:
            self.chat_panel.show_confirmation(
                raw_request.detail,
                raw_request.confirm,
                raw_request.reject,
            )

    @Slot()
    def toggle_overlay(self) -> None:
        """Toggle only when the attached process owns the foreground window."""
        if self.overlay.isVisible():
            self.overlay.hide()
            return
        identity = self.controller.attached_identity()
        if identity is None or self._hotkeys.foreground_pid() != identity.pid:
            return
        self.overlay.set_ai_enabled(self.orchestrator is not None and self.orchestrator.available)
        if self.orchestrator is None:
            self.overlay.set_history(())
        else:
            self.overlay.set_history(
                tuple(
                    (message.role, message.text)
                    for message in self.orchestrator.conversation.messages
                )
            )
        self.overlay.show_for_process(
            identity,
            self._last_write_access,
            self.controller.list_watches(),
        )
        self._refresh_overlay_trainers()

    @Slot()
    def _refresh_overlay_watches(self) -> None:
        self.overlay.refresh_watches(self.controller.list_watches())

    @Slot()
    def _refresh_overlay_trainers(self) -> None:
        identity = self.controller.attached_identity()
        if identity is None:
            self.overlay.refresh_trainer_tricks(())
            return
        try:
            states = self.controller.list_trainer_tricks(Actor.USER)
        except Exception as exc:
            self.overlay.refresh_trainer_tricks(())
            self.overlay.set_operation_result(str(exc), error=True)
            return
        self.overlay.refresh_trainer_tricks(states)

    @Slot(str)
    def _create_manual_trainer(self, watch_id: str) -> None:
        from_overlay = self.sender() is self.overlay
        entry = self._watch_entry(watch_id)
        if entry is None:
            self._report_manual_trainer_result(t("overlay.no_watches"), from_overlay, True)
            return
        if not self._last_write_access:
            self._report_manual_trainer_result(t("overlay.read_only"), from_overlay, True)
            return
        if entry.frozen:
            self._report_manual_trainer_result(
                t("trainer.manual.unfreeze_first"), from_overlay, True
            )
            return
        dialog = TrainerDialog(entry, self.overlay if from_overlay else self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        draft = dialog.draft()
        try:
            address = self.controller.watch_address(watch_id, Actor.USER)
            current = self.controller.read_address(address, entry.data_type)
            confirmation = ConfirmDialog(
                action=t("trainer.manual.confirm", name=draft.name),
                address=address,
                data_type=entry.data_type,
                current_value=current,
                new_value=draft.enabled_value,
                allow_remember=False,
                parent=self.overlay if from_overlay else self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
            if current != draft.enabled_value:
                self.controller.set_watch_value(
                    watch_id,
                    draft.enabled_value,
                    Actor.USER,
                )
            self.controller.save_trainer_trick(
                watch_id,
                name=draft.name,
                enabled_value=draft.enabled_value,
                disabled_value=draft.disabled_value,
                mode=draft.mode,
                interval_ms=draft.interval_ms,
                notes=draft.notes,
                actor=Actor.USER,
            )
        except Exception as exc:
            self._report_manual_trainer_result(str(exc), from_overlay, True)
            return
        self._report_manual_trainer_result(
            t("trainer.manual.saved", name=draft.name), from_overlay, False
        )
        self._refresh_overlay_watches()
        self._refresh_overlay_trainers()

    @Slot(str, str, object)
    def _overlay_save_trainer_values(
        self,
        trick_id: str,
        enabled_value: str,
        raw_disabled_value: object,
    ) -> None:
        if not self._overlay_mutations_allowed():
            return
        disabled_value = raw_disabled_value if isinstance(raw_disabled_value, str) else None
        try:
            self.controller.update_trainer_trick_values(
                trick_id,
                enabled_value=enabled_value,
                disabled_value=disabled_value,
                actor=Actor.USER,
            )
        except Exception as exc:
            self.overlay.set_operation_result(str(exc), error=True)
            return
        self.overlay.set_operation_result(t("overlay.trainer.values_saved"))
        self._refresh_overlay_trainers()

    def _report_manual_trainer_result(
        self,
        message: str,
        from_overlay: bool,
        error: bool,
    ) -> None:
        if from_overlay:
            self.overlay.set_operation_result(message, error=error)
            return
        if error:
            self.show_error(message)
            return
        self.status_strip.set_message(message, "success")

    @Slot(str, bool)
    def _overlay_toggle_trick(self, trick_id: str, active: bool) -> None:
        if not self._overlay_mutations_allowed():
            return
        try:
            state = next(
                (
                    item
                    for item in self.controller.list_trainer_tricks(Actor.USER)
                    if item.trick.id == trick_id
                ),
                None,
            )
            if not isinstance(state, TrainerTrickState):
                identity = self.controller.attached_identity()
                process_name = identity.name if identity is not None else "—"
                self.overlay.set_operation_result(
                    t("overlay.no_trainers", name=process_name),
                    error=True,
                )
                return
            trick = state.trick
            address = self.controller.trainer_trick_address(trick_id, Actor.USER)
            needs_confirmation = active or trick.mode is TrickMode.WRITE_PAIR
            if needs_confirmation:
                current = self.controller.read_address(address, trick.data_type)
                new_value = (
                    trick.enabled_value if active else trick.disabled_value or trick.enabled_value
                )
                confirmation = ConfirmDialog(
                    action=t(
                        "overlay.trainer.activate_confirm"
                        if active
                        else "overlay.trainer.deactivate_confirm",
                        name=trick.name,
                    ),
                    address=address,
                    data_type=trick.data_type,
                    current_value=current,
                    new_value=new_value,
                    allow_remember=False,
                    parent=self.overlay,
                )
                if confirmation.exec() != QDialog.DialogCode.Accepted:
                    return
            self.controller.set_trainer_trick_active(trick_id, active, Actor.USER)
        except Exception as exc:
            self.overlay.set_operation_result(str(exc), error=True)
            return
        self.overlay.set_operation_result(
            t("overlay.trainer.activated" if active else "overlay.trainer.deactivated")
        )
        self._refresh_overlay_trainers()

    @Slot(str, str)
    def _overlay_write_watch(self, watch_id: str, value: str) -> None:
        if not self._overlay_mutations_allowed():
            return
        entry = self._watch_entry(watch_id)
        if entry is None:
            self.overlay.set_operation_result(t("overlay.no_watches"), error=True)
            return
        try:
            address = self.controller.watch_address(watch_id, Actor.USER)
            if self._write_confirmation_enabled:
                confirmation = ConfirmDialog(
                    action=t("overlay.write_confirm"),
                    address=address,
                    data_type=entry.data_type,
                    current_value=entry.current_value,
                    new_value=value,
                    allow_remember=True,
                    parent=self.overlay,
                )
                if confirmation.exec() != QDialog.DialogCode.Accepted:
                    return
                if confirmation.remember_for_session:
                    self._write_confirmation_enabled = False
            self.controller.set_watch_value(watch_id, value, Actor.USER)
        except Exception as exc:
            self.overlay.set_operation_result(str(exc), error=True)
            return
        self.overlay.set_operation_result(t("overlay.write_ok"))
        self._refresh_overlay_watches()

    @Slot(str, str, bool)
    def _overlay_set_freeze(self, watch_id: str, value: str, frozen: bool) -> None:
        if not self._overlay_mutations_allowed():
            return
        entry = self._watch_entry(watch_id)
        if entry is None:
            self.overlay.set_operation_result(t("overlay.no_watches"), error=True)
            return
        try:
            if frozen:
                address = self.controller.watch_address(watch_id, Actor.USER)
                confirmation = ConfirmDialog(
                    action=t("overlay.freeze_confirm"),
                    address=address,
                    data_type=entry.data_type,
                    current_value=entry.current_value,
                    new_value=value,
                    allow_remember=False,
                    parent=self.overlay,
                )
                if confirmation.exec() != QDialog.DialogCode.Accepted:
                    return
            self.controller.set_freeze(
                watch_id,
                frozen,
                value if frozen else entry.desired_value,
                entry.interval_ms,
                Actor.USER,
            )
        except Exception as exc:
            self.overlay.set_operation_result(str(exc), error=True)
            return
        self.overlay.set_operation_result(
            t("overlay.freeze_ok") if frozen else t("overlay.unfreeze_ok")
        )
        self._refresh_overlay_watches()

    def _watch_entry(self, watch_id: str) -> WatchEntry | None:
        return next(
            (entry for entry in self.controller.list_watches() if entry.id == watch_id),
            None,
        )

    def _overlay_mutations_allowed(self) -> bool:
        current = self.controller.attached_identity()
        bound = self.overlay.bound_identity
        if current is None or bound is None or not current.matches(bound):
            self.overlay.set_operation_result(t("overlay.no_process"), error=True)
            return False
        if not self._last_write_access:
            self.overlay.set_operation_result(t("overlay.read_only"), error=True)
            return False
        return True

    @Slot()
    def select_process(self) -> None:
        dialog = AttachDialog(self.controller, self.settings.ui.show_system_processes, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.identity is not None:
            self._last_write_access = dialog.write_access
            self.top_bar.set_attached(dialog.identity, dialog.write_access)
            self.status_strip.set_message(
                t("status.attached_ok", name=dialog.identity.name, pid=dialog.identity.pid),
                "success",
            )
            self._refresh_modules()
            if self.orchestrator is not None:
                self.orchestrator.note_write_access(dialog.write_access)

    @Slot()
    def detach_process(self) -> None:
        try:
            self.controller.detach(t("status.detached_by_user"), Actor.USER)
        except Exception as exc:
            self.show_error(exc)

    @Slot(object)
    def start_first_scan(self, request: object) -> None:
        if not isinstance(request, ScanRequest):
            return
        try:
            self.controller.start_scan(request, Actor.USER)
        except Exception as exc:
            self.show_error(exc)

    @Slot(object)
    def start_next_scan(self, request: object) -> None:
        if not isinstance(request, ScanRequest):
            return
        try:
            self.controller.refine_scan(request, Actor.USER)
        except Exception as exc:
            self.show_error(exc)

    @Slot()
    def reset_scan(self) -> None:
        try:
            self.controller.reset_scan()
        except Exception as exc:
            self.show_error(exc)
            return
        self.results_view.clear()
        self.scan_panel.reset_form_state()
        self.scan_panel.set_session_state(
            SessionState.NEW, self.controller.attached_identity() is not None
        )
        self.status_strip.set_message(t("status.scan_reset"))

    @Slot(object)
    def add_result_watch(self, raw_row: object) -> None:
        if not isinstance(raw_row, CandidateRow):
            return
        try:
            self.controller.add_watch(
                WatchSpec(
                    label=format_hex(raw_row.address),
                    data_type=raw_row.data_type,
                    address=raw_row.address,
                    interval_ms=self.settings.ui.watch_refresh_ms,
                ),
                Actor.USER,
            )
        except Exception as exc:
            self.show_error(exc)

    @Slot(object)
    def edit_result_value(self, raw_row: object) -> None:
        if not isinstance(raw_row, CandidateRow):
            return
        value, accepted = QInputDialog.getText(
            self,
            t("results.edit.title"),
            t("results.edit.prompt", address=format_hex(raw_row.address)),
            text=raw_row.current,
        )
        if not accepted or not value.strip():
            return
        if self._write_confirmation_enabled:
            confirmation = ConfirmDialog(
                action=t("confirm.manual_write"),
                address=raw_row.address,
                data_type=raw_row.data_type,
                current_value=raw_row.current,
                new_value=value.strip(),
                allow_remember=True,
                parent=self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
            if confirmation.remember_for_session:
                self._write_confirmation_enabled = False
        try:
            self.controller.write_address(
                raw_row.address, raw_row.data_type, value.strip(), Actor.USER
            )
        except Exception as exc:
            self.show_error(exc)
            return
        self.results_view.reload()

    @Slot(object, object)
    def reinterpret_result(self, raw_row: object, raw_type: object) -> None:
        if not isinstance(raw_row, CandidateRow) or not isinstance(raw_type, DataType):
            return
        try:
            value = self.controller.read_address(raw_row.address, raw_type)
        except Exception as exc:
            self.show_error(exc)
            return
        self.status_strip.set_message(
            t(
                "results.reinterpreted",
                address=format_hex(raw_row.address),
                type=t(f"data_type.{raw_type.value}"),
                value=value,
            )
        )

    @Slot()
    def save_workspace(self) -> None:
        self.watch_view.save_workspace_button.click()

    @Slot()
    def load_workspace(self) -> None:
        self.watch_view.load_workspace_button.click()

    @Slot()
    def launch_memory_lab(self) -> None:
        try:
            pid = self.controller.launch_memory_lab()
        except Exception as exc:
            self.show_error(exc)
            return
        answer = QMessageBox.question(
            self,
            t("action.memory_lab"),
            t("lab.attach_question", pid=pid),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            identity = self.controller.attach(pid, True, Actor.USER)
        except Exception as exc:
            self.show_error(exc)
            return
        self._last_write_access = True
        self.top_bar.set_attached(identity, True)
        self._refresh_modules()
        if self.orchestrator is not None:
            self.orchestrator.note_write_access(True)

    @Slot()
    def open_settings(self) -> None:
        if self.orchestrator is not None and self.orchestrator.busy:
            self.show_error(
                MemPilotError(
                    "Espera a que termine la respuesta actual antes de cambiar los ajustes."
                )
            )
            return
        dialog = SettingsDialog(self.settings, self.settings_service, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings = dialog.settings
        if self.orchestrator is not None:
            provider = create_cli_provider(self.settings.ai)
            self.orchestrator.configure_provider(provider, self.settings.ai)
            self.chat_panel.set_ai_enabled(self.orchestrator.available)
            self.chat_panel.set_mode(self.orchestrator.policy.mode.value)
            self.overlay.set_ai_enabled(self.orchestrator.available)
        self.status_strip.set_message(t("settings.saved"), "success")

    @Slot()
    def show_help(self) -> None:
        QMessageBox.information(self, t("help.title"), t("help.body"))

    @Slot(object)
    def show_error(self, exc: object) -> None:
        error = exc if isinstance(exc, BaseException) else MemPilotError(str(exc))
        ErrorDialog(error, self).exec()

    @Slot(object)
    def _on_attached(self, _identity: object) -> None:
        if self.controller.attached_identity() is None:
            return
        self.top_bar.set_attached(self.controller.attached_identity(), self._last_write_access)  # type: ignore[arg-type]
        self.scan_panel.set_session_state(SessionState.NEW, True)
        self.results_view.clear()
        self._refresh_modules()

    @Slot(str)
    def _on_detached(self, reason: str) -> None:
        self._last_write_access = False
        self.overlay.hide()
        self.top_bar.set_detached()
        self.scan_panel.set_session_state(SessionState.NEW, False)
        self.results_view.clear()
        self.results_view.set_modules([])
        self.status_strip.finish_scan(reason)

    @Slot(int)
    def _on_process_lost(self, pid: int) -> None:
        self._last_write_access = False
        self.overlay.hide()
        self.status_strip.finish_scan(t("status.process_lost", pid=pid), "error")

    @Slot(object)
    def _on_scan_started(self, request: object) -> None:
        del request
        self.scan_panel.set_session_state(SessionState.SCANNING, True)
        self.status_strip.start_scan()

    @Slot(object)
    def _on_scan_progress(self, progress: object) -> None:
        if not isinstance(progress, ScanProgress):
            return
        self.status_strip.update_progress(progress)
        self.scan_panel.update_stats(self.controller.scan_status())

    @Slot(object)
    def _on_scan_finished(self, session: object) -> None:
        if not isinstance(session, ScanSession):
            return
        status = self.controller.scan_status()
        self.scan_panel.set_session_state(SessionState.READY, True)
        self.scan_panel.update_stats(status)
        self.results_view.reload(reset_offset=True)
        self.status_strip.finish_scan(
            t("status.scan_complete", count=f"{status.candidates:,}".replace(",", ".")),
            "success",
        )
        self._refresh_modules()

    @Slot(str)
    def _on_scan_failed(self, message: str) -> None:
        self.scan_panel.set_session_state(SessionState.ERROR, True)
        self.status_strip.finish_scan(message or t("status.failed"), "error")

    @Slot()
    def _on_scan_cancelled(self) -> None:
        self.scan_panel.set_session_state(SessionState.CANCELLED, True)
        self.status_strip.finish_scan(t("status.cancelled"), "warning")

    @Slot(str)
    def _on_watch_error(self, message: str) -> None:
        self.status_strip.set_message(message, "error")

    @Slot(bool, int, int)
    def _on_autonomous_changed(self, active: bool, used: int, limit: int) -> None:
        identity = self.controller.attached_identity()
        self.chat_panel.set_autonomous_state(
            active,
            identity.name if identity is not None else "",
            identity.pid if identity is not None else 0,
            used,
            limit,
        )

    @Slot(object)
    def _workspace_saved(self, path: object) -> None:
        if isinstance(path, Path):
            self.status_strip.set_message(t("status.workspace_saved", path=str(path)), "success")

    @Slot(object)
    def _workspace_loaded(self, path: object) -> None:
        if isinstance(path, Path):
            self.status_strip.set_message(t("status.workspace_loaded", path=str(path)), "success")

    def _refresh_modules(self) -> None:
        try:
            modules = self.controller.list_modules(Actor.USER)
        except Exception:
            self.results_view.set_modules([])
            return
        self.results_view.set_modules([module.name for module in modules])

    def _restore_layout(self) -> None:
        geometry = self._layout_settings.value("main/geometry", QByteArray())
        horizontal = self._layout_settings.value("main/hsplitter", QByteArray())
        vertical = self._layout_settings.value("main/vsplitter", QByteArray())
        header = self._layout_settings.value("results/header", QByteArray())
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            self.restoreGeometry(geometry)
        if isinstance(horizontal, QByteArray) and not horizontal.isEmpty():
            self.horizontal_splitter.restoreState(horizontal)
        if isinstance(vertical, QByteArray) and not vertical.isEmpty():
            self.vertical_splitter.restoreState(vertical)
        if isinstance(header, QByteArray) and not header.isEmpty():
            self.results_view.table.horizontalHeader().restoreState(header)

    def _save_layout(self) -> None:
        self._layout_settings.setValue("main/geometry", self.saveGeometry())
        self._layout_settings.setValue("main/hsplitter", self.horizontal_splitter.saveState())
        self._layout_settings.setValue("main/vsplitter", self.vertical_splitter.saveState())
        self._layout_settings.setValue(
            "results/header", self.results_view.table.horizontalHeader().saveState()
        )
        self._layout_settings.sync()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._native_hotkeys_enabled or self._hotkeys_registered:
            return
        failed = self._hotkeys.register(int(self.winId()))
        self._hotkeys_registered = True
        if failed:
            self.status_strip.set_message(
                t("overlay.hotkey_failed", shortcuts=", ".join(failed)),
                "warning",
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Persist layout, release hotkeys, and shut down every worker."""
        application = QApplication.instance()
        if application is not None and self._native_hotkeys_enabled:
            application.removeNativeEventFilter(self._hotkey_filter)
        self._save_layout()
        self._hotkeys.unregister()
        self.overlay.close()
        self.controller.shutdown()
        event.accept()
