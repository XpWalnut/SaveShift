from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from app.database.models.installed_game import InstalledGame
from app.ui import theme, styles


class InstalledGameCard(QFrame):
    selected = Signal(object)

    def __init__(
        self,
        installed_game: InstalledGame,
        project_count: int,
        is_selected: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.installed_game = installed_game
        self.is_selected = is_selected

        self.setObjectName("InstalledGameCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()

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

    def mousePressEvent(self, event) -> None:
        self.selected.emit(self.installed_game)
        super().mousePressEvent(event)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            styles.card_style(
                "InstalledGameCard",
                selected=self.is_selected,
            )
        )