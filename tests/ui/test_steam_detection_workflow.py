from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from app.games.game_id import GameId
from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService
from app.ui.main_window import MainWindow


def test_detect_steam_games_button_registers_and_discovers_games(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    window = MainWindow()
    qtbot.addWidget(window)
    installed_game = InstalledGameService.add_installed_game(
        game_id=GameId.SCHEDULE_I.value,
        display_name="Schedule I",
        save_path=str(tmp_path / "Saves"),
    )
    discovery_calls: list[int] = []
    refreshes: list[str] = []
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        InstalledGameService,
        "detect_steam_games",
        lambda: [installed_game],
    )
    monkeypatch.setattr(
        ProjectService,
        "discover_projects",
        lambda installed_game_id: discovery_calls.append(installed_game_id),
    )
    monkeypatch.setattr(
        window,
        "load_installed_games",
        lambda: refreshes.append("games"),
    )
    monkeypatch.setattr(
        window,
        "load_projects",
        lambda: refreshes.append("projects"),
    )
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    qtbot.mouseClick(window.detect_games_button, Qt.MouseButton.LeftButton)

    assert discovery_calls == [installed_game.id]
    assert refreshes == ["games", "projects"]
    assert window.selected_installed_game_id == installed_game.id
    assert messages == [("Steam Games Detected", "Added: Schedule I")]
