import json
from pathlib import Path

from app.database.repositories.project_repository import ProjectRepository
from app.games.game_id import GameId
from app.services.installed_game_service import InstalledGameService
from app.services.project_service import ProjectService


def test_schedule_i_discovery_persists_project_once_in_test_database(
    tmp_path: Path,
) -> None:
    save_root = tmp_path / "Schedule I" / "Saves"
    save_folder = save_root / "76561198044844170" / "SaveGame_1"
    players_folder = save_folder / "Players" / "Player_0"
    players_folder.mkdir(parents=True)
    (save_folder / "Game.json").write_text(
        json.dumps(
            {
                "DataType": "Game",
                "OrganisationName": "Database Test Empire",
            }
        ),
        encoding="utf-8",
    )
    (save_folder / "Metadata.json").write_text(
        json.dumps({"GameVersion": "0.4.5f2"}),
        encoding="utf-8",
    )
    (players_folder / "Player.json").write_text(
        '{"DataType": "Player"}',
        encoding="utf-8",
    )
    installed_game = InstalledGameService.add_installed_game(
        game_id=GameId.SCHEDULE_I.value,
        display_name="Schedule I",
        save_path=str(save_root),
    )

    first_discovery = ProjectService.discover_projects(installed_game.id)
    second_discovery = ProjectService.discover_projects(installed_game.id)
    persisted = ProjectRepository.get_for_installed_game(installed_game.id)

    assert len(first_discovery) == 1
    assert len(second_discovery) == 1
    assert len(persisted) == 1
    assert persisted[0].id == first_discovery[0].id
    assert persisted[0].uuid == first_discovery[0].uuid
    assert persisted[0].name == "Database Test Empire"
    assert persisted[0].local_path == str(save_folder)
