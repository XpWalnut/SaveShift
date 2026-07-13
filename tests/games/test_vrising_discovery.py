import json
from pathlib import Path

from app.games.vrising.discovery import VRisingDiscovery


def test_discovers_vrising_world_with_display_name(
    temp_save_root: Path,
) -> None:
    world_folder = (
        temp_save_root
        / "76561198044844170"
        / "v4"
        / "5c30111e-ebce-4af2-9c32-f27b098e4ff2"
    )
    world_folder.mkdir(parents=True)

    settings_file = world_folder / "ServerHostSettings.json"
    settings_file.write_text(
        json.dumps(
            {
                "Name": "XpWalnut's World",
                "Password": "3326",
            }
        ),
        encoding="utf-8",
    )

    autosave_file = world_folder / "AutoSave_2415.save.gz"
    autosave_file.write_bytes(b"save-data")

    discovery = VRisingDiscovery()

    projects = discovery.discover_projects(temp_save_root)

    assert len(projects) == 1

    project = projects[0]

    assert project.name == "XpWalnut's World"
    assert project.root_path == world_folder
    assert set(project.save_files) == {
        settings_file,
        autosave_file,
    }
    assert project.metadata["steam_user_id"] == "76561198044844170"
    assert project.metadata["world_uuid"] == (
        "5c30111e-ebce-4af2-9c32-f27b098e4ff2"
    )
    assert project.metadata["file_count"] == 2


def test_vrising_discovery_excludes_backup_and_temp_files(
    temp_save_root: Path,
) -> None:
    world_folder = (
        temp_save_root
        / "76561198044844170"
        / "v4"
        / "world-uuid"
    )
    backup_folder = world_folder / ".BACKUP"
    temp_folder = world_folder / ".TEMP"

    backup_folder.mkdir(parents=True)
    temp_folder.mkdir(parents=True)

    settings_file = world_folder / "ServerHostSettings.json"
    settings_file.write_text(
        json.dumps({"Name": "Main World"}),
        encoding="utf-8",
    )

    active_save = world_folder / "AutoSave_1.save.gz"
    active_save.write_bytes(b"active")

    backup_save = backup_folder / "AutoSave_0.save.gz"
    backup_save.write_bytes(b"backup")

    temp_save = temp_folder / "AutoSave_2.save.gz"
    temp_save.write_bytes(b"temp")

    discovery = VRisingDiscovery()

    projects = discovery.discover_projects(temp_save_root)

    assert len(projects) == 1

    project = projects[0]

    assert set(project.save_files) == {
        settings_file,
        active_save,
    }
    assert project.metadata["file_count"] == 2


def test_vrising_discovery_falls_back_to_world_uuid(
    temp_save_root: Path,
) -> None:
    world_folder = (
        temp_save_root
        / "76561198044844170"
        / "v4"
        / "fallback-world-uuid"
    )
    world_folder.mkdir(parents=True)

    invalid_settings = world_folder / "ServerHostSettings.json"
    invalid_settings.write_text(
        "{not valid json",
        encoding="utf-8",
    )

    save_file = world_folder / "AutoSave_1.save.gz"
    save_file.write_bytes(b"save-data")

    discovery = VRisingDiscovery()

    projects = discovery.discover_projects(temp_save_root)

    assert len(projects) == 1
    assert projects[0].name == "fallback-world-uuid"


def test_ignores_empty_vrising_world(
    temp_save_root: Path,
) -> None:
    empty_world = (
        temp_save_root
        / "76561198044844170"
        / "v4"
        / "empty-world"
    )
    empty_world.mkdir(parents=True)

    discovery = VRisingDiscovery()

    projects = discovery.discover_projects(temp_save_root)

    assert projects == []