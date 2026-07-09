from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from app.database.models.installed_game import InstalledGame
from app.ui import theme


class InstalledGameCard(QFrame):
    def __init__(
        self,
        installed_game: InstalledGame,
        project_count: int,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName("InstalledGameCard")
        self.setStyleSheet(
            f"""
            QFrame#InstalledGameCard {{
                background-color: {theme.CARD_BACKGROUND};
                border: 1px solid {theme.CARD_BORDER};
                border-radius: {theme.CARD_RADIUS}px;
                padding: {theme.SPACING}px;
            }}

            QLabel {{
                color: {theme.TEXT_PRIMARY};
            }}

            QLabel#SecondaryText {{
                color: {theme.TEXT_SECONDARY};
            }}
            """
        )

        title = QLabel(f"🎮 {installed_game.display_name}")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")

        subtitle = QLabel(
            f"{project_count} project{'s' if project_count != 1 else ''} tracked"
        )
        subtitle.setObjectName("SecondaryText")

        layout = QVBoxLayout()
        layout.setSpacing(theme.SPACING_SMALL)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.setLayout(layout)