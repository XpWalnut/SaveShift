from pathlib import Path

import pytest

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


def test_discovers_chunked_directory_world_and_ignores_automatic_backup(
    temp_save_root: Path,
) -> None:
    world = temp_save_root / "New World"
    world.mkdir()
    database = world / "_main.8.db2"
    metadata = world / "_main.8.fwl2"
    chunks = world / "_main.8.chunks"
    region = world / "20_20__1_4.chunk"
    for path in (database, metadata, chunks, region):
        path.write_bytes(path.name.encode())

    backup = temp_save_root / "New World_backup_auto-20260910-112253"
    backup.mkdir()
    (backup / "_main.1.db2").write_bytes(b"backup")
    (backup / "_main.1.fwl2").write_bytes(b"backup")

    projects = ValheimDiscovery().discover_projects(temp_save_root)

    assert [project.name for project in projects] == ["New World"]
    assert projects[0].root_path == world
    assert set(projects[0].save_files) == {database, metadata, chunks, region}
    assert projects[0].metadata == {
        "file_count": 4,
        "storage_layout": "chunked_directory",
        "world_directory": "New World",
    }


def test_chunked_import_target_preserves_world_directory(temp_save_root: Path) -> None:
    target = ValheimDiscovery().get_import_target(
        temp_save_root,
        "Display Name",
        {
            "storage_layout": "chunked_directory",
            "world_directory": "New World",
        },
    )

    assert target.project_root == temp_save_root / "New World"


@pytest.mark.parametrize("world_directory", ["../escape", "nested/world", "nested\\world"])
def test_chunked_import_target_rejects_unsafe_directory(
    temp_save_root: Path,
    world_directory: str,
) -> None:
    with pytest.raises(ValueError, match="invalid world directory"):
        ValheimDiscovery().get_import_target(
            temp_save_root,
            "World",
            {
                "storage_layout": "chunked_directory",
                "world_directory": world_directory,
            },
        )
