"""Credential access with environment-first precedence."""

import os
from contextlib import suppress
from typing import Literal

import keyring
from keyring.errors import PasswordDeleteError

KEYRING_SERVICE = "MemPilot"
KEYRING_USER = "openai_api_key"


def _environment_key() -> str | None:
    value = os.environ.get("OPENAI_API_KEY")
    return value if value else None


def resolve_api_key() -> str | None:
    """Resolve the API key from the environment, then the operating-system keyring."""
    environment_key = _environment_key()
    if environment_key is not None:
        return environment_key
    stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    return stored if stored else None


def store_api_key(key: str) -> None:
    """Store an API key in the operating-system keyring."""
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)


def clear_api_key() -> None:
    """Remove the stored API key; do nothing when no key exists."""
    with suppress(PasswordDeleteError):
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)


def key_source() -> Literal["entorno", "keyring", "ninguna"]:
    """Report the source that would currently provide the API key."""
    if _environment_key() is not None:
        return "entorno"
    return "keyring" if keyring.get_password(KEYRING_SERVICE, KEYRING_USER) else "ninguna"
