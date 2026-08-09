"""Manual trainer creation dialog independent of any AI provider."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mempilot.core.data_types import encode_value
from mempilot.core.watcher import WatchEntry
from mempilot.i18n import t
from mempilot.services.trainer_service import TrickMode
from mempilot.ui.theme import monospace_font


@dataclass(frozen=True, slots=True)
class TrainerDraft:
    """Validated values entered for one manual trainer trick."""

    name: str
    enabled_value: str
    disabled_value: str | None
    mode: TrickMode
    interval_ms: int
    notes: str


class TrainerDialog(QDialog):
    """Collect and validate a reversible trainer definition for one watch."""

    def __init__(self, watch: WatchEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._watch = watch
        self.setWindowTitle(t("trainer.manual.title"))
        self.setModal(True)
        self.setMinimumWidth(440)

        self.name_edit = QLineEdit(watch.label, self)
        self.type_label = QLabel(t(f"data_type.{watch.data_type.value}"), self)
        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem(t("overlay.trainer.mode.freeze"), TrickMode.FREEZE)
        self.mode_combo.addItem(t("overlay.trainer.mode.write_pair"), TrickMode.WRITE_PAIR)
        self.enabled_edit = QLineEdit(watch.desired_value or watch.current_value, self)
        self.enabled_edit.setFont(monospace_font())
        self.disabled_edit = QLineEdit(self)
        self.disabled_edit.setFont(monospace_font())
        self.interval_spin = QSpinBox(self)
        self.interval_spin.setRange(50, 5000)
        self.interval_spin.setSingleStep(50)
        self.interval_spin.setValue(watch.interval_ms)
        self.interval_spin.setSuffix(t("watch.interval_suffix"))
        self.notes_edit = QLineEdit(watch.notes, self)
        self.error_label = QLabel("", self)
        self.error_label.setProperty("tone", "error")
        self.error_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow(t("trainer.manual.name"), self.name_edit)
        form.addRow(t("trainer.manual.type"), self.type_label)
        form.addRow(t("trainer.manual.mode"), self.mode_combo)
        form.addRow(t("trainer.manual.enabled"), self.enabled_edit)
        form.addRow(t("trainer.manual.disabled"), self.disabled_edit)
        form.addRow(t("trainer.manual.interval"), self.interval_spin)
        form.addRow(t("trainer.manual.notes"), self.notes_edit)
        self.disabled_label = form.labelForField(self.disabled_edit)

        self.save_button = QPushButton(t("trainer.manual.save"), self)
        self.save_button.setProperty("primary", True)
        self.save_button.clicked.connect(self._validate_and_accept)
        self.cancel_button = QPushButton(t("trainer.manual.cancel"), self)
        self.cancel_button.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        actions.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(actions)

        self.mode_combo.currentIndexChanged.connect(self._sync_mode)
        self._sync_mode()

    def draft(self) -> TrainerDraft:
        """Return the validated trainer values currently shown by the dialog."""
        name = self.name_edit.text().strip()
        if not name:
            raise ValueError(t("trainer.manual.name_required"))
        enabled = self.enabled_edit.text().strip()
        if not enabled:
            raise ValueError(t("trainer.manual.enabled_required"))
        try:
            mode = TrickMode(self.mode_combo.currentData())
        except (TypeError, ValueError) as exc:
            raise ValueError(t("trainer.manual.enabled_required")) from exc
        disabled = self.disabled_edit.text().strip() if mode is TrickMode.WRITE_PAIR else None
        if mode is TrickMode.WRITE_PAIR and not disabled:
            raise ValueError(t("trainer.manual.disabled_required"))
        for value in (enabled, disabled):
            if value is None:
                continue
            try:
                encode_value(self._watch.data_type, value)
            except Exception as exc:
                raise ValueError(
                    t(
                        "trainer.manual.invalid_value",
                        type=t(f"data_type.{self._watch.data_type.value}"),
                    )
                ) from exc
        return TrainerDraft(
            name=name,
            enabled_value=enabled,
            disabled_value=disabled,
            mode=mode,
            interval_ms=self.interval_spin.value(),
            notes=self.notes_edit.text().strip(),
        )

    @Slot()
    def _sync_mode(self) -> None:
        write_pair = self.mode_combo.currentData() == TrickMode.WRITE_PAIR.value
        self.disabled_edit.setVisible(write_pair)
        if self.disabled_label is not None:
            self.disabled_label.setVisible(write_pair)

    @Slot()
    def _validate_and_accept(self) -> None:
        try:
            self.draft()
        except ValueError as exc:
            self.error_label.setText(str(exc))
            return
        self.accept()
