import json
from pathlib import Path

import pytest

from app.games.game_id import GameId
from app.games.registry import GameRegistry
from app.games.schedule_i.definition import ScheduleIGame
from app.games.schedule_i.discovery import ScheduleIDiscovery


STEAM_USER_ID = "76561198044844170"


def _create_save(
    save_root: Path,
    slot_number: int,
    *,
    organization_name: str | None = None,
) -> Path:
    save_folder = (
        save_root
        / STEAM_USER_ID
        / f"SaveGame_{slot_number}"
    )
    players_folder = save_folder / "Players" / "Player_0"
    players_folder.mkdir(parents=True)
    (players_folder / "Player.json").write_text(
        '{"DataType": "Player"}',
        encoding="utf-8",
    )
    game_data = {"DataType": "Game"}

    if organization_name is not None:
        game_data["OrganisationName"] = organization_name

    (save_folder / "Game.json").write_text(
        json.dumps(game_data),
        encoding="utf-8",
    )
    (save_folder / "Metadata.json").write_text(
        json.dumps({"GameVersion": "0.4.5f2"}),
        encoding="utf-8",
    )
    return save_folder


def test_discovers_schedule_i_save_with_organization_name(
    temp_save_root: Path,
) -> None:
    save_folder = _create_save(
        temp_save_root,
        1,
        organization_name="Honda Odyssey Inc",
    )

    projects = ScheduleIDiscovery().discover_projects(temp_save_root)

    assert len(projects) == 1
    project = projects[0]
    assert project.name == "Honda Odyssey Inc"
    assert project.root_path == save_folder
    assert set(project.save_files) == {
        save_folder / "Game.json",
        save_folder / "Metadata.json",
        save_folder / "Players" / "Player_0" / "Player.json",
    }
    assert project.metadata == {
        "steam_user_id": STEAM_USER_ID,
        "save_slot": 1,
        "game_version": "0.4.5f2",
        "file_count": 3,
    }


def test_discovery_falls_back_to_save_slot_and_ignores_invalid_folders(
    temp_save_root: Path,
) -> None:
    save_folder = _create_save(temp_save_root, 2)
    invalid_folder = temp_save_root / STEAM_USER_ID / "Autosaves"
    invalid_folder.mkdir()
    (invalid_folder / "ignored.json").write_text("{}", encoding="utf-8")

    projects = ScheduleIDiscovery().discover_projects(temp_save_root)

    assert len(projects) == 1
    assert projects[0].name == "Save Game 2"
    assert projects[0].root_path == save_folder


def test_import_reuses_save_with_matching_organization(
    temp_save_root: Path,
) -> None:
    save_folder = _create_save(
        temp_save_root,
        3,
        organization_name="Shared Empire",
    )

    target = ScheduleIDiscovery().get_import_target(
        temp_save_root,
        "Shared Empire",
    )

    assert target.project_root == save_folder


def test_import_uses_first_available_save_slot(
    temp_save_root: Path,
) -> None:
    _create_save(temp_save_root, 1, organization_name="First")
    _create_save(temp_save_root, 3, organization_name="Third")

    target = ScheduleIDiscovery().get_import_target(
        temp_save_root,
        "Incoming Empire",
    )

    assert target.project_root == (
        temp_save_root / STEAM_USER_ID / "SaveGame_2"
    )


def test_import_rejects_ambiguous_steam_profiles(
    temp_save_root: Path,
) -> None:
    (temp_save_root / STEAM_USER_ID).mkdir()
    (temp_save_root / "76561198000000000").mkdir()

    with pytest.raises(
        RuntimeError,
        match="which Steam profile",
    ):
        ScheduleIDiscovery().get_import_target(
            temp_save_root,
            "Incoming Empire",
        )


def test_import_rejects_duplicate_organization_names(
    temp_save_root: Path,
) -> None:
    _create_save(temp_save_root, 1, organization_name="Shared Empire")
    _create_save(temp_save_root, 2, organization_name="Shared Empire")

    with pytest.raises(RuntimeError, match="Multiple Schedule I saves"):
        ScheduleIDiscovery().get_import_target(
            temp_save_root,
            "Shared Empire",
        )


def test_import_rejects_when_all_save_slots_are_occupied(
    temp_save_root: Path,
) -> None:
    for slot_number in range(1, 6):
        _create_save(
            temp_save_root,
            slot_number,
            organization_name=f"Empire {slot_number}",
        )

    with pytest.raises(RuntimeError, match="All Schedule I save slots"):
        ScheduleIDiscovery().get_import_target(
            temp_save_root,
            "Incoming Empire",
        )


def test_schedule_i_is_registered_with_steam_metadata() -> None:
    game = GameRegistry.get_by_game_id(GameId.SCHEDULE_I)

    assert game is not None
    assert game.display_name == "Schedule I"
    assert game.steam_app_id == 3164500
    assert game.process_names == ["Schedule I.exe"]


def test_schedule_i_detects_existing_default_save_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_path = (
        tmp_path
        / "AppData"
        / "LocalLow"
        / "TVGS"
        / "Schedule I"
        / "Saves"
    )
    save_path.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert ScheduleIGame().detect_save_path() == save_path
