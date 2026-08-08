"""Append-only local audit trail with bounded rotation."""

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from PySide6.QtCore import QObject, Signal

from mempilot.config.paths import AUDIT_FILE
from mempilot.logging_setup import redact_secrets

AUDIT_ROTATION_BYTES = 5_000_000
FREEZE_HEARTBEAT_SECONDS = 5.0


class AuditRecord(BaseModel):
    """One user-visible or agent-visible audited action."""

    model_config = ConfigDict(extra="forbid")

    ts: datetime
    actor: str
    action: str
    target: str
    detail: str
    result: str


class AuditService(QObject):
    """Write audit records and aggregate high-frequency freeze writes."""

    audit_appended = Signal(object)

    def __init__(
        self,
        path: Path | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self._path = path if path is not None else AUDIT_FILE
        self._clock = clock
        self._lock = threading.RLock()
        self._freeze_writes = 0
        self._freeze_actor = "system"
        self._freeze_target = "vigilancias"
        self._freeze_detail = ""
        self._freeze_window_started: float | None = None

    @property
    def path(self) -> Path:
        """Return the active audit JSONL path."""
        return self._path

    def record(
        self,
        actor: str,
        action: str,
        target: str,
        detail: str,
        result: str,
    ) -> AuditRecord:
        """Append one redacted audit record and emit it to observers."""
        record = AuditRecord(
            ts=datetime.now(UTC),
            actor=redact_secrets(actor),
            action=redact_secrets(action),
            target=redact_secrets(target),
            detail=redact_secrets(detail),
            result=redact_secrets(result),
        )
        self._append(record)
        return record

    def record_freeze_writes(
        self,
        count: int,
        *,
        actor: str = "system",
        target: str = "vigilancias",
        detail: str = "",
    ) -> AuditRecord | None:
        """Aggregate freeze ticks and append at most one heartbeat every five seconds."""
        if count < 0:
            raise ValueError("El número de escrituras no puede ser negativo")
        with self._lock:
            now = self._clock()
            if count:
                if self._freeze_window_started is None:
                    self._freeze_window_started = now
                self._freeze_writes += count
                self._freeze_actor = redact_secrets(actor)
                self._freeze_target = redact_secrets(target)
                self._freeze_detail = redact_secrets(detail)
            if self._freeze_window_started is None:
                return None
            if now - self._freeze_window_started < FREEZE_HEARTBEAT_SECONDS:
                return None
            return self._flush_freeze_locked(now)

    def flush(self) -> AuditRecord | None:
        """Persist a pending freeze heartbeat, if any."""
        with self._lock:
            return self._flush_freeze_locked(self._clock())

    def _flush_freeze_locked(self, now: float) -> AuditRecord | None:
        if self._freeze_writes == 0:
            self._freeze_window_started = None
            return None
        writes = self._freeze_writes
        started = self._freeze_window_started if self._freeze_window_started is not None else now
        elapsed = max(0.0, now - started)
        detail = f"{writes} escrituras de congelado agregadas en {elapsed:.1f} s"
        if self._freeze_detail:
            detail = f"{detail}; {self._freeze_detail}"
        record = AuditRecord(
            ts=datetime.now(UTC),
            actor=self._freeze_actor,
            action="freeze_heartbeat",
            target=self._freeze_target,
            detail=detail,
            result="ok",
        )
        self._freeze_writes = 0
        self._freeze_window_started = None
        self._append_locked(record)
        self.audit_appended.emit(record)
        return record

    def _append(self, record: AuditRecord) -> None:
        with self._lock:
            self._append_locked(record)
        self.audit_appended.emit(record)

    def _append_locked(self, record: AuditRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = record.model_dump_json() + "\n"
        encoded_size = len(line.encode("utf-8"))
        current_size = self._path.stat().st_size if self._path.exists() else 0
        if current_size and current_size + encoded_size > AUDIT_ROTATION_BYTES:
            rotated = self._path.with_name(f"{self._path.stem}.1{self._path.suffix}")
            self._path.replace(rotated)
        with self._path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
