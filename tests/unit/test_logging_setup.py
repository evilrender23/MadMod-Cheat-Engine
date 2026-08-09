"""Focused tests for application log redaction."""

import logging
from pathlib import Path

import pytest

import mempilot.logging_setup as logging_setup


def test_secret_redaction_filter_removes_keys_from_log_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logging_setup, "LOG_DIR", tmp_path)
    log_path = logging_setup.setup_logging(logging.INFO)
    root = logging.getLogger()
    secret_in_message = "sk-message-secret-123456789"
    secret_in_argument = "sk-argument-secret-987654321"

    try:
        logger = logging.getLogger("mempilot.tests.logging.unique")
        logger.warning("provider=%s key=%s", secret_in_message, secret_in_argument)
        for handler in root.handlers:
            handler.flush()
    finally:
        for handler in tuple(root.handlers):
            if handler.get_name() == "mempilot_rotating_file":
                root.removeHandler(handler)
                handler.close()

    raw = log_path.read_text(encoding="utf-8")
    assert secret_in_message not in raw
    assert secret_in_argument not in raw
    assert raw.count("***") == 2
