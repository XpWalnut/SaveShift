from app.ui import theme


def primary_button_style() -> str:
    return f"""
    QPushButton {{
        background-color: {theme.ACCENT};
        color: {theme.TEXT_PRIMARY};
        border: none;
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
        background-color: {theme.CARD_BACKGROUND};
        color: {theme.TEXT_PRIMARY};
        border: 1px solid {theme.CARD_BORDER};
        border-radius: {theme.BUTTON_RADIUS}px;
        min-height: 34px;
        padding: 4px 14px;
        font-weight: bold;
    }}

    QPushButton:hover {{
        background-color: {theme.ACCENT};
    }}

    QPushButton:pressed {{
        background-color: {theme.ACCENT_PRESSED};
    }}
    """


def card_style(object_name: str, selected: bool = False) -> str:
    border = theme.ACCENT if selected else theme.CARD_BORDER
    border_width = 2 if selected else 1

    return f"""
    QFrame#{object_name} {{
        background-color: {theme.CARD_BACKGROUND};
        border: {border_width}px solid {border};
        border-radius: {theme.CARD_RADIUS}px;
        padding: {theme.SPACING}px;
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