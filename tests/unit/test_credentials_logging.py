"""Focused tests for credential precedence and log redaction."""

import logging
from pathlib import Path

import pytest

import mempilot.logging_setup as logging_setup
from mempilot.services import credentials


def test_environment_key_takes_precedence_over_keyring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-environment-unique-1234")
    monkeypatch.setattr(
        credentials.keyring,
        "get_password",
        lambda *_args: pytest.fail("keyring must not be read when environment is configured"),
    )

    assert credentials.resolve_api_key() == "sk-environment-unique-1234"
    assert credentials.key_source() == "entorno"


def test_keyring_is_used_when_environment_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        credentials.keyring,
        "get_password",
        lambda service, user: "sk-keyring-unique-5678",
    )

    assert credentials.resolve_api_key() == "sk-keyring-unique-5678"
    assert credentials.key_source() == "keyring"


def test_missing_or_empty_credentials_report_no_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(credentials.keyring, "get_password", lambda *_args: None)

    assert credentials.resolve_api_key() is None
    assert credentials.key_source() == "ninguna"


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
        logger = logging.getLogger("mempilot.tests.credentials.unique")
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
