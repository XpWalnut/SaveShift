from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy

from app.database.models.installed_game import InstalledGame
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.widgets.installed_game_card import InstalledGameCard


def test_installed_game_list_reserves_space_before_vertical_scrollbar(
    qtbot,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    window = MainWindow()
    qtbot.addWidget(window)

    margins = window.installed_game_layout.contentsMargins()

    assert margins.right() == theme.SPACING
    assert (
        window.installed_game_scroll.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )


def test_installed_game_card_expands_to_available_viewport_width(qtbot) -> None:
    card = InstalledGameCard(
        installed_game=InstalledGame(
            id=1,
            game_id="abiotic_factor",
            display_name="Abiotic Factor",
            save_path="unused-test-path",
            enabled=True,
        ),
        project_count=1,
        is_selected=False,
    )
    qtbot.addWidget(card)

    assert card.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
