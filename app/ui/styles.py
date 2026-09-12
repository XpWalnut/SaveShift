from app.ui import theme


def application_style() -> str:
    return f"""
    QWidget {{
        color: {theme.TEXT_PRIMARY};
        background-color: {theme.WINDOW_BACKGROUND};
        font-family: "Consolas", "Segoe UI";
        font-size: 13px;
    }}

    QDialog, QMainWindow {{
        background-color: {theme.WINDOW_BACKGROUND};
    }}

    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QListWidget, QTabWidget::pane {{
        background-color: {theme.PANEL_BACKGROUND};
        color: {theme.TEXT_PRIMARY};
        border: 1px solid {theme.CARD_BORDER};
        border-radius: {theme.BUTTON_RADIUS}px;
        padding: 6px;
        selection-background-color: {theme.ACCENT};
    }}

    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
    QListWidget:focus {{
        border: 1px solid {theme.CYAN};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {theme.CYAN};
        background: {theme.PANEL_BACKGROUND};
    }}

    QCheckBox::indicator:checked {{
        background: {theme.ACCENT};
        border-color: {theme.ACCENT_HOVER};
    }}

    QScrollBar:vertical {{
        background: {theme.PANEL_BACKGROUND};
        width: 10px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 0, y2: 1,
            stop: 0 {theme.ORANGE}, stop: 1 {theme.ACCENT}
        );
        min-height: 28px;
        border-radius: 4px;
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QToolTip {{
        color: {theme.TEXT_PRIMARY};
        background-color: {theme.PANEL_BACKGROUND};
        border: 1px solid {theme.CYAN};
        padding: 6px;
    }}
    """


def primary_button_style() -> str:
    return f"""
    QPushButton {{
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 {theme.PURPLE}, stop: 1 {theme.ACCENT}
        );
        color: {theme.TEXT_PRIMARY};
        border: 1px solid {theme.ACCENT_HOVER};
        border-radius: {theme.BUTTON_RADIUS}px;
        min-height: 34px;
        padding: 4px 14px;
        font-weight: bold;
    }}

    QPushButton:hover {{
        background-color: {theme.ACCENT_HOVER};
    }}

    QPushButton:pressed {{
        background-color: {theme.ACCENT_PRESSED};
    }}
    """


def secondary_button_style() -> str:
    return f"""
    QPushButton {{
        background-color: {theme.PANEL_BACKGROUND};
        color: {theme.TEXT_PRIMARY};
        border: 1px solid {theme.CYAN};
        border-radius: {theme.BUTTON_RADIUS}px;
        min-height: 34px;
        padding: 4px 14px;
        font-weight: bold;
    }}

    QPushButton:hover {{
        background-color: {theme.CARD_BACKGROUND};
        border-color: {theme.CYAN_HOVER};
        color: {theme.CYAN_HOVER};
    }}

    QPushButton:pressed {{
        background-color: {theme.ACCENT_PRESSED};
    }}
    """


def card_style(object_name: str, selected: bool = False) -> str:
    border = theme.CYAN if selected else theme.CARD_BORDER
    border_width = 2 if selected else 1

    return f"""
    QFrame#{object_name} {{
        background-color: {theme.CARD_BACKGROUND};
        border: {border_width}px solid {border};
        border-radius: {theme.CARD_RADIUS}px;
        padding: {theme.SPACING}px;
    }}

    QFrame#{object_name}:hover {{
        border-color: {theme.ORANGE_HOVER};
    }}

    QLabel {{
        color: {theme.TEXT_PRIMARY};
        background-color: transparent;
    }}

    QLabel#SecondaryText {{
        color: {theme.TEXT_SECONDARY};
        background-color: transparent;
    }}
    """
