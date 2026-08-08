"""MemPilot application palette, tokens, and focused widget styling."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

WINDOW = QColor("#202225")
BASE = QColor("#17191C")
ALTERNATE_BASE = QColor("#25282C")
TEXT = QColor("#E6E8EB")
BUTTON = QColor("#2B2E33")
HIGHLIGHT = QColor("#3D6F9E")
HIGHLIGHTED_TEXT = QColor("#FFFFFF")
PLACEHOLDER = QColor("#8A9099")
DISABLED = QColor("#70757D")
AMBER = QColor("#E0A32E")
AMBER_TINT = QColor(224, 163, 46, 36)
PRIMARY = QColor("#5B9BD5")
SUCCESS = QColor("#4FAF6D")
ERROR = QColor("#D65C5C")
BORDER = QColor("#3A3D42")

# Spacing uses a 4 px base; widgets compose only these values.
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_6 = 24
RADIUS = 3
ROW_HEIGHT = 22


def monospace_font() -> QFont:
    """Return Consolas when available and the platform fixed font otherwise."""
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    if not font.exactMatch():
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(9)
    return font


def build_palette() -> QPalette:
    """Build the complete graphite Fusion palette."""
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: WINDOW,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: BASE,
        QPalette.ColorRole.AlternateBase: ALTERNATE_BASE,
        QPalette.ColorRole.ToolTipBase: BUTTON,
        QPalette.ColorRole.ToolTipText: TEXT,
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: BUTTON,
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.BrightText: TEXT,
        QPalette.ColorRole.Link: PRIMARY,
        QPalette.ColorRole.LinkVisited: PRIMARY,
        QPalette.ColorRole.Highlight: HIGHLIGHT,
        QPalette.ColorRole.HighlightedText: HIGHLIGHTED_TEXT,
        QPalette.ColorRole.PlaceholderText: PLACEHOLDER,
        QPalette.ColorRole.Light: BUTTON,
        QPalette.ColorRole.Midlight: BUTTON,
        QPalette.ColorRole.Mid: BUTTON,
        QPalette.ColorRole.Dark: BASE,
        QPalette.ColorRole.Shadow: BASE,
    }
    for role, color in roles.items():
        palette.setColor(QPalette.ColorGroup.Active, role, color)
        palette.setColor(QPalette.ColorGroup.Inactive, role, color)
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.PlaceholderText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, DISABLED)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, BUTTON)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, DISABLED)
    return palette


QSS = """
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #3A3D42;
}
QGroupBox {
    border: 1px solid #3A3D42;
    border-radius: 3px;
    margin-top: 8px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QAbstractItemView {
    border: 1px solid #3A3D42;
    gridline-color: #3A3D42;
}
QHeaderView::section {
    border: 0;
    border-right: 1px solid #3A3D42;
    border-bottom: 1px solid #3A3D42;
    min-height: 22px;
    padding: 0 8px;
}
QTableView::item, QTreeView::item {
    min-height: 22px;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    border: 1px solid #3A3D42;
    border-radius: 3px;
    min-height: 22px;
    padding: 0 4px;
}
QLineEdit[validationError="true"], QDoubleSpinBox[validationError="true"] {
    border-color: #D65C5C;
}
QPushButton, QToolButton {
    border: 1px solid #3A3D42;
    border-radius: 3px;
    min-height: 22px;
    padding: 0 8px;
}
QPushButton:hover, QToolButton:hover, QLineEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #5B9BD5;
}
QPushButton[primary="true"] {
    border-color: #5B9BD5;
}
QLabel[tone="error"] { color: #D65C5C; }
QLabel[tone="warning"] { color: #E0A32E; }
QLabel[tone="success"] { color: #4FAF6D; }
QFrame[card="true"] {
    border: 1px solid #3A3D42;
    border-radius: 3px;
}
"""


def apply_theme(app: QApplication) -> None:
    """Apply Fusion, the complete palette, system type, then focused QSS."""
    app.setStyle("Fusion")
    font = app.font()
    font.setPointSize(9)
    app.setFont(font)
    app.setPalette(build_palette())
    app.setStyleSheet(QSS)
