"""Branded startup splash for the desktop application."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QSplashScreen

from mempilot.branding import APP_NAME, LOGO_FILENAME, PRODUCT_NAME, asset_path
from mempilot.i18n import t

_SPLASH_WIDTH = 520
_SPLASH_HEIGHT = 520
_LOGO_SIZE = 460


def create_splash() -> QSplashScreen:
    """Build the fixed branded splash from the packaged logo."""
    canvas = QPixmap(_SPLASH_WIDTH, _SPLASH_HEIGHT)
    canvas.fill(QColor("#080A0D"))
    logo = QPixmap(str(asset_path(LOGO_FILENAME)))
    if logo.isNull():
        raise RuntimeError(t("error.logo_load"))
    scaled_logo = logo.scaled(
        _LOGO_SIZE,
        _LOGO_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    logo_x = (_SPLASH_WIDTH - scaled_logo.width()) // 2
    painter.drawPixmap(logo_x, 30, scaled_logo)
    painter.end()

    splash = QSplashScreen(canvas, Qt.WindowType.WindowStaysOnTopHint)
    splash.setObjectName("madModEngineSplash")
    splash.setWindowTitle(f"{APP_NAME} — {PRODUCT_NAME}")
    return splash
