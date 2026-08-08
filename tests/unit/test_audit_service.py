"""Focused tests for JSONL auditing, rotation, and freeze aggregation."""

import json
from pathlib import Path

from mempilot.services.audit_service import AUDIT_ROTATION_BYTES, AuditService


def test_audit_writes_one_json_object_per_line(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    service = AuditService(path)

    emitted = []
    service.audit_appended.connect(emitted.append)
    record = service.record(
        actor="user",
        action="freeze_on",
        target="watch-health-audit-unique",
        detail="valor deseado 100",
        result="ok",
    )

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["action"] == "freeze_on"
    assert document["target"] == "watch-health-audit-unique"
    assert emitted == [record]


def test_audit_redacts_accidental_credentials(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    secret = "sk-audit-secret-123456789"

    AuditService(path).record("user", "provider", "settings", secret, "error")

    raw = path.read_text(encoding="utf-8")
    assert secret not in raw
    assert "***" in raw


def test_audit_rotates_before_exceeding_five_megabytes(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_bytes(b"x" * AUDIT_ROTATION_BYTES)
    service = AuditService(path)

    service.record("agent", "write_watch", "watch-rotation-unique", "42", "ok")

    rotated = tmp_path / "audit.1.jsonl"
    assert rotated.stat().st_size == AUDIT_ROTATION_BYTES
    assert json.loads(path.read_text(encoding="utf-8"))["action"] == "write_watch"


def test_freeze_writes_emit_one_aggregated_heartbeat_per_window(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    current_time = [100.0]
    service = AuditService(path, clock=lambda: current_time[0])

    assert service.record_freeze_writes(1, target="freeze-group-unique") is None
    current_time[0] = 104.0
    assert service.record_freeze_writes(2, target="freeze-group-unique") is None
    current_time[0] = 105.0

    heartbeat = service.record_freeze_writes(3, target="freeze-group-unique")

    assert heartbeat is not None
    assert heartbeat.action == "freeze_heartbeat"
    assert "6 escrituras" in heartbeat.detail
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["target"] == "freeze-group-unique"


def test_flush_persists_pending_freeze_writes(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    service = AuditService(path, clock=lambda: 1.0)
    service.record_freeze_writes(4, detail="cierre ordenado")

    heartbeat = service.flush()

    assert heartbeat is not None
    assert "4 escrituras" in path.read_text(encoding="utf-8")
