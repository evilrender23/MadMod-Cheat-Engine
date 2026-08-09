"""Application logging with rotation and credential redaction."""

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from mempilot.config.paths import LOG_DIR

_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{12,}")
_HANDLER_NAME = "mempilot_rotating_file"


def redact_secrets(text: str) -> str:
    """Replace credential-shaped secret keys in text with a safe marker."""
    return _SECRET_PATTERN.sub("***", text)


class SecretRedactionFilter(logging.Filter):
    """Redact credential-shaped strings from log messages and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.msg)
        if record.args:
            record.args = _redact(record.args)
        return True


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    return value


def setup_logging(level: str | int = logging.INFO) -> Path:
    """Install the application rotating file handler and return its path."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "mempilot.log"
    root = logging.getLogger()
    root.setLevel(level)

    for existing in tuple(root.handlers):
        if existing.get_name() == _HANDLER_NAME:
            root.removeHandler(existing)
            existing.close()

    handler = RotatingFileHandler(
        log_path,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.set_name(_HANDLER_NAME)
    handler.setLevel(level)
    handler.addFilter(SecretRedactionFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    return log_path
