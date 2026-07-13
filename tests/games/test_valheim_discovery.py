from pathlib import Path

from app.games.valheim.discovery import ValheimDiscovery


def test_discovers_valheim_world_with_db_and_fwl(
    temp_save_root: Path,
) -> None:
    db_file = temp_save_root / "Mistwalkers.db"
    fwl_file = temp_save_root / "Mistwalkers.fwl"

    db_file.write_text("database-data", encoding="utf-8")
    fwl_file.write_text("world-metadata", encoding="utf-8")

    discovery = ValheimDiscovery()

    projects = discovery.discover_projects(temp_save_root)

    assert len(projects) == 1

    project = projects[0]

    assert project.name == "Mistwalkers"
    assert project.root_path == temp_save_root
    assert project.save_files == [
        db_file,
        fwl_file,
    ]
    assert project.metadata["file_count"] == 2


def test_discovers_valheim_world_without_fwl(
    temp_save_root: Path,
) -> None:
    db_file = temp_save_root / "SoloWorld.db"
    db_file.write_text("database-data", encoding="utf-8")

    discovery = ValheimDiscovery()

    projects = discovery.discover_projects(temp_save_root)

    assert len(projects) == 1

    project = projects[0]

    assert project.name == "SoloWorld"
    assert project.root_path == temp_save_root
    assert project.save_files == [db_file]
    assert project.metadata["file_count"] == 1


def test_ignores_valheim_fwl_without_matching_db(
    temp_save_root: Path,
) -> None:
    orphan_fwl = temp_save_root / "OrphanWorld.fwl"
    orphan_fwl.write_text("world-metadata", encoding="utf-8")

    discovery = ValheimDiscovery()

    projects = discovery.discover_projects(temp_save_root)

    assert projects == []