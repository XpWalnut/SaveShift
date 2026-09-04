import json
from pathlib import Path

import pytest

from app.database.repositories.installed_game_repository import (
    InstalledGameRepository,
)
from app.database.repositories.project_repository import ProjectRepository
from app.games.game_id import GameId
from app.games.registry import GameRegistry
from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService


def _create_schedule_i_installation(steam_root: Path) -> None:
    steamapps = steam_root / "steamapps"
    (steamapps / "common" / "Schedule I").mkdir(parents=True)
    (steamapps / "appmanifest_3164500.acf").write_text(
        (
            '"AppState"\n'
            "{\n"
            '    "appid" "3164500"\n'
            '    "installdir" "Schedule I"\n'
            "}\n"
        ),
        encoding="utf-8",
    )


def _create_schedule_i_save(save_root: Path) -> Path:
    save_folder = save_root / "76561198044844170" / "SaveGame_1"
    (save_folder / "Players" / "Player_0").mkdir(parents=True)
    (save_folder / "Game.json").write_text(
        json.dumps({"OrganisationName": "Detected Test Empire"}),
        encoding="utf-8",
    )
    return save_folder


def test_steam_detection_registers_game_and_discovers_save_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steam_root = tmp_path / "Steam"
    save_root = tmp_path / "Schedule I" / "Saves"
    save_folder = _create_schedule_i_save(save_root)
    _create_schedule_i_installation(steam_root)
    schedule_i = GameRegistry.get_by_game_id(GameId.SCHEDULE_I)
    assert schedule_i is not None
    monkeypatch.setattr(schedule_i, "detect_save_path", lambda: save_root)

    added_games = InstalledGameService.detect_steam_games(steam_root)
    assert len(added_games) == 1
    discovered = ProjectService.discover_projects(added_games[0].id)

    assert InstalledGameService.detect_steam_games(steam_root) == []
    persisted_games = InstalledGameRepository.get_all()
    persisted_projects = ProjectRepository.get_for_installed_game(
        added_games[0].id
    )
    assert len(persisted_games) == 1
    assert persisted_games[0].game_id == GameId.SCHEDULE_I.value
    assert persisted_games[0].save_path == str(save_root)
    assert len(discovered) == 1
    assert len(persisted_projects) == 1
    assert persisted_projects[0].name == "Detected Test Empire"
    assert persisted_projects[0].local_path == str(save_folder)
