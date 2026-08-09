"""Filesystem locations for mutable application data."""

import os
from pathlib import Path

_APPDATA = os.environ.get("APPDATA")
APP_DIR = Path(_APPDATA) / "MemPilot" if _APPDATA else Path.home() / ".mempilot"
LOG_DIR = APP_DIR / "logs"
WORKSPACE_DIR = APP_DIR / "workspaces"
TRAINER_DIR = APP_DIR / "trainers"
SETTINGS_FILE = APP_DIR / "settings.json"
AUDIT_FILE = LOG_DIR / "audit.jsonl"


def ensure_dirs() -> None:
    """Create all application-owned directories."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    TRAINER_DIR.mkdir(parents=True, exist_ok=True)


def repo_root() -> Path:
    """Return the source repository root when running unbundled."""
    return Path(__file__).resolve().parents[3]
