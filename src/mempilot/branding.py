"""Product identity and packaged visual-resource lookup."""

from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "M@D-Engine"
PRODUCT_NAME = "Mad Mod Engine"
ORGANIZATION_NAME = "Mad Mod Engine"
ORGANIZATION_DOMAIN = "madmod.engine"
APP_DATA_DIRECTORY = "M@D-Engine"
LOGO_FILENAME = "logo.png"


def asset_path(filename: str) -> Path:
    """Resolve one bundled asset in source and PyInstaller executions."""
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        bundle_root = Path(__file__).resolve().parents[2]
    return bundle_root / "assets" / filename
