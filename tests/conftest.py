"""Shared pytest configuration."""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip platform-specific tests with an explicit reason."""
    if "windows" in item.keywords and sys.platform != "win32":
        pytest.skip(f"Requiere Windows: las APIs Win32 no existen en {sys.platform}")
