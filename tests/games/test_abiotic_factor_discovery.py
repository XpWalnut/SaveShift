from pathlib import Path

from app.games.abiotic_factor.discovery import AbioticFactorDiscovery


def test_discovers_abiotic_factor_world(
    temp_save_root: Path,
) -> None:
    steam_user = temp_save_root / "76561198044844170"
    world_folder = steam_user / "Worlds" / "First"
    nested_folder = world_folder / "PlayerData"

    nested_folder.mkdir(parents=True)

    world_file = world_folder / "World.sav"
    player_file = nested_folder / "Player.sav"

    world_file.write_text("world-data", encoding="utf-8")
    player_file.write_text("player-data", encoding="utf-8")

    discovery = AbioticFactorDiscovery()

    projects = discovery.discover_projects(temp_save_root)

    assert len(projects) == 1

    project = projects[0]

    assert project.name == "First"
    assert project.root_path == world_folder
    assert set(project.save_files) == {
        world_file,
        player_file,
    }
    assert project.metadata["steam_user_id"] == "76561198044844170"
    assert project.metadata["file_count"] == 2


def test_ignores_empty_abiotic_factor_world(
    temp_save_root: Path,
) -> None:
    empty_world = (
        temp_save_root
        / "76561198044844170"
        / "Worlds"
        / "Empty"
    )
    empty_world.mkdir(parents=True)

    discovery = AbioticFactorDiscovery()

    projects = discovery.discover_projects(temp_save_root)

    assert projects == []