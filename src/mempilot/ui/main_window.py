"""Main MemPilot window and complete GUI-to-controller wiring."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, Qt, Slot
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mempilot.config.settings import Settings
from mempilot.controller import Actor, AppController
from mempilot.core.data_types import DataType, format_hex
from mempilot.core.exceptions import MemPilotError
from mempilot.core.scan_session import CandidateRow, ScanSession, SessionState
from mempilot.core.scanner import ScanProgress, ScanRequest
from mempilot.core.watcher import WatchSpec
from mempilot.i18n import t
from mempilot.services.settings_service import SettingsService
from mempilot.ui.dialogs.attach_dialog import AttachDialog
from mempilot.ui.dialogs.confirm_dialog import ConfirmDialog
from mempilot.ui.dialogs.error_dialog import ErrorDialog
from mempilot.ui.dialogs.settings_dialog import SettingsDialog
from mempilot.ui.widgets.chat_panel import ChatPanel
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
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.settings = settings or Settings()
        self.settings_service = settings_service or SettingsService()
        self._layout_settings = QSettings("MemPilot", "MemPilot")
        self._write_confirmation_enabled = True
        self._last_write_access = False
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
        # Wave 3 will enable the provider; the local no-AI experience is complete now.
        self.chat_panel = ChatPanel(ai_enabled=False, parent=central)
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

    def _install_global_actions(self) -> None:
        specs = (
            ("attach", "Ctrl+P", self.select_process),
            ("save", "Ctrl+S", self.save_workspace),
            ("load", "Ctrl+O", self.load_workspace),
            ("lab", "Ctrl+L", self.launch_memory_lab),
            ("help", "F1", self.show_help),
        )
        self.global_actions: dict[str, QAction] = {}
        for name, sequence, callback in specs:
            action = QAction(self)
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

    @Slot()
    def select_process(self) -> None:
        dialog = AttachDialog(self.controller, self.settings.ui.show_system_processes, self)
        if dialog.exec() is QDialog.DialogCode.Accepted and dialog.identity is not None:
            self._last_write_access = dialog.write_access
            self.top_bar.set_attached(dialog.identity, dialog.write_access)
            self.status_strip.set_message(
                t("status.attached_ok", name=dialog.identity.name, pid=dialog.identity.pid),
                "success",
            )
            self._refresh_modules()

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
            if confirmation.exec() is not QDialog.DialogCode.Accepted:
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
        if answer is not QMessageBox.StandardButton.Yes:
            return
        try:
            identity = self.controller.attach(pid, True, Actor.USER)
        except Exception as exc:
            self.show_error(exc)
            return
        self._last_write_access = True
        self.top_bar.set_attached(identity, True)
        self._refresh_modules()

    @Slot()
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.settings_service, self)
        if dialog.exec() is QDialog.DialogCode.Accepted:
            self.settings = dialog.settings
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
        self.top_bar.set_detached()
        self.scan_panel.set_session_state(SessionState.NEW, False)
        self.results_view.clear()
        self.results_view.set_modules([])
        self.status_strip.finish_scan(reason)

    @Slot(int)
    def _on_process_lost(self, pid: int) -> None:
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

    def closeEvent(self, event: QCloseEvent) -> None:
        """Persist layout and shut down every worker before accepting close."""
        self._save_layout()
        self.controller.shutdown()
        event.accept()
