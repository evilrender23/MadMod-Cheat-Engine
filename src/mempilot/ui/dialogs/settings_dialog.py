"""Validated persistent settings editor."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mempilot.config.settings import Settings
from mempilot.i18n import t
from mempilot.services.settings_service import SettingsService
from mempilot.ui.dialogs.error_dialog import ErrorDialog
from mempilot.ui.theme import SPACE_2, SPACE_3


class SettingsDialog(QDialog):
    """Edit Settings through typed controls and atomically persist on acceptance."""

    def __init__(
        self,
        settings: Settings,
        service: SettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self.settings = settings.model_copy(deep=True)
        self.setWindowTitle(t("settings.title"))
        self.setModal(True)
        self.setMinimumWidth(580)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)
        tabs = QTabWidget(self)
        tabs.setAccessibleName(t("settings.title"))
        tabs.addTab(self._scan_tab(), t("settings.scan_tab"))
        tabs.addTab(self._ui_tab(), t("settings.ui_tab"))
        tabs.addTab(self._ai_tab(), t("settings.ai_tab"))
        layout.addWidget(tabs)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(t("action.cancel"), self)
        cancel.setAccessibleName(t("action.cancel"))
        cancel.clicked.connect(self.reject)
        save = QPushButton(t("settings.save"), self)
        save.setAccessibleName(t("settings.save"))
        save.setProperty("primary", True)
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _scan_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.unknown_budget = QSpinBox(page)
        self.unknown_budget.setAccessibleName(t("settings.unknown_budget"))
        self.unknown_budget.setRange(1, 1_048_576)
        self.unknown_budget.setValue(self.settings.scan.unknown_budget_mb)
        self.unknown_budget.setSuffix(" MB")
        form.addRow(t("settings.unknown_budget"), self.unknown_budget)
        self.max_candidates = QSpinBox(page)
        self.max_candidates.setAccessibleName(t("settings.max_candidates"))
        self.max_candidates.setRange(1, 100_000_000)
        self.max_candidates.setValue(self.settings.scan.max_candidates)
        form.addRow(t("settings.max_candidates"), self.max_candidates)
        return page

    def _ui_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.page_size = QSpinBox(page)
        self.page_size.setAccessibleName(t("settings.results_page_size"))
        self.page_size.setRange(1, 100_000)
        self.page_size.setValue(self.settings.ui.results_page_size)
        form.addRow(t("settings.results_page_size"), self.page_size)
        self.results_refresh = QSpinBox(page)
        self.results_refresh.setAccessibleName(t("settings.results_refresh"))
        self.results_refresh.setRange(50, 5000)
        self.results_refresh.setValue(self.settings.ui.results_refresh_ms)
        self.results_refresh.setSuffix(" ms")
        form.addRow(t("settings.results_refresh"), self.results_refresh)
        self.watch_refresh = QSpinBox(page)
        self.watch_refresh.setAccessibleName(t("settings.watch_refresh"))
        self.watch_refresh.setRange(50, 5000)
        self.watch_refresh.setValue(self.settings.ui.watch_refresh_ms)
        self.watch_refresh.setSuffix(" ms")
        form.addRow(t("settings.watch_refresh"), self.watch_refresh)
        self.show_system = QCheckBox(t("settings.show_system"), page)
        self.show_system.setAccessibleName(t("settings.show_system"))
        self.show_system.setChecked(self.settings.ui.show_system_processes)
        form.addRow("", self.show_system)
        return page

    def _ai_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self.ai_enabled = QCheckBox(t("settings.ai_enabled"), page)
        self.ai_enabled.setAccessibleName(t("settings.ai_enabled"))
        self.ai_enabled.setChecked(self.settings.ai.enabled)
        form.addRow("", self.ai_enabled)
        self.model_edit = QLineEdit(self.settings.ai.model, page)
        self.model_edit.setAccessibleName(t("settings.model"))
        form.addRow(t("settings.model"), self.model_edit)
        self.base_url_edit = QLineEdit(self.settings.ai.base_url or "", page)
        self.base_url_edit.setAccessibleName(t("settings.base_url"))
        form.addRow(t("settings.base_url"), self.base_url_edit)
        self.timeout_spin = QDoubleSpinBox(page)
        self.timeout_spin.setAccessibleName(t("settings.timeout"))
        self.timeout_spin.setRange(0.1, 3600.0)
        self.timeout_spin.setValue(self.settings.ai.timeout_s)
        self.timeout_spin.setSuffix(" s")
        form.addRow(t("settings.timeout"), self.timeout_spin)
        self.retries_spin = QSpinBox(page)
        self.retries_spin.setAccessibleName(t("settings.retries"))
        self.retries_spin.setRange(0, 20)
        self.retries_spin.setValue(self.settings.ai.max_retries)
        form.addRow(t("settings.retries"), self.retries_spin)
        self.write_limit = QSpinBox(page)
        self.write_limit.setAccessibleName(t("settings.write_limit"))
        self.write_limit.setRange(0, 100_000)
        self.write_limit.setValue(self.settings.ai.autonomous_write_limit)
        form.addRow(t("settings.write_limit"), self.write_limit)
        return page

    def _save(self) -> None:
        updated = self.settings.model_copy(deep=True)
        updated.scan.unknown_budget_mb = self.unknown_budget.value()
        updated.scan.max_candidates = self.max_candidates.value()
        updated.ui.results_page_size = self.page_size.value()
        updated.ui.results_refresh_ms = self.results_refresh.value()
        updated.ui.watch_refresh_ms = self.watch_refresh.value()
        updated.ui.show_system_processes = self.show_system.isChecked()
        updated.ai.enabled = self.ai_enabled.isChecked()
        updated.ai.model = self.model_edit.text().strip() or "gpt-4.1"
        updated.ai.base_url = self.base_url_edit.text().strip() or None
        updated.ai.timeout_s = self.timeout_spin.value()
        updated.ai.max_retries = self.retries_spin.value()
        updated.ai.autonomous_write_limit = self.write_limit.value()
        try:
            self._service.save(updated)
        except Exception as exc:
            ErrorDialog(exc, self).exec()
            return
        self.settings = updated
        self.accept()
