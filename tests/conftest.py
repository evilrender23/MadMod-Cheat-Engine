"""Shared pytest configuration."""

import os
import sys
from collections.abc import Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _reset_interface_language() -> Iterator[None]:
    """Keep the process-wide translation catalog isolated between tests."""
    from mempilot.i18n import Language, set_language

    set_language(Language.SPANISH)
    yield
    set_language(Language.SPANISH)


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip platform-specific tests with an explicit reason."""
    if "windows" in item.keywords and sys.platform != "win32":
        pytest.skip(f"Requiere Windows: las APIs Win32 no existen en {sys.platform}")
