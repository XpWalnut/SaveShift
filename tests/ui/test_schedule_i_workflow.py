from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.settings import AppSettings
from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.games.game_id import GameId
from app.games.registry import GameRegistry
from app.services.hosting_service import HostingService
from app.ui.main_window import MainWindow


def test_hosting_schedule_i_launches_the_steam_game(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.settings = AppSettings(
        player_display_name="Bob",
        coordination_enabled=False,
    )
    project = Project(
        id=1,
        installed_game_id=1,
        name="Honda Odyssey Inc",
        local_path=str(tmp_path / "SaveGame_1"),
        uuid="12345678-1234-4678-9234-567812345678",
    )
    installed_game = InstalledGame(
        id=1,
        game_id=GameId.SCHEDULE_I.value,
        display_name="Schedule I",
        save_path=str(tmp_path / "Saves"),
        enabled=True,
    )
    game = GameRegistry.get_by_game_id(GameId.SCHEDULE_I)
    assert game is not None
    launch_calls: list[bool] = []
    messages: list[tuple[str, str]] = []

    monkeypatch.setattr(
        window,
        "_get_installed_game_for_project",
        lambda _project: installed_game,
    )
    monkeypatch.setattr(window, "load_installed_games", lambda: None)
    monkeypatch.setattr(window, "load_projects", lambda: None)
    monkeypatch.setattr(
        HostingService,
        "host_project",
        lambda **_kwargs: SimpleNamespace(
            version_number=1,
            package_path=tmp_path / "schedule-i.sspkg",
        ),
    )
    monkeypatch.setattr(game, "is_running", lambda: False)
    monkeypatch.setattr(game, "launch", lambda: launch_calls.append(True))
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window.host_project(project)

    assert launch_calls == [True]
    assert len(messages) == 1
    assert messages[0][0] == "Project Hosted"
    assert "Schedule I is launching through Steam" in messages[0][1]
