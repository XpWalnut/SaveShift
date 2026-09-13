from pathlib import Path
from types import SimpleNamespace

import pytest

from app.games.game_id import GameId
from app.services.save_file_service import SaveFileService


def _project(name: str, root: Path):
    return SimpleNamespace(name=name, local_path=str(root))


def test_flat_valheim_listing_contains_only_selected_world(tmp_path: Path) -> None:
    selected_db = tmp_path / "Selected.db"
    selected_fwl = tmp_path / "Selected.fwl"
    other_db = tmp_path / "Other.db"
    selected_db.write_bytes(b"selected")
    selected_fwl.write_bytes(b"metadata")
    other_db.write_bytes(b"other")

    files = SaveFileService.list_project_files(
        _project("Selected", tmp_path),
        GameId.VALHEIM.value,
    )

    assert set(files) == {selected_db, selected_fwl}


def test_flat_valheim_backup_contains_only_selected_world(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "worlds_local"
    root.mkdir()
    (root / "Selected.db").write_bytes(b"selected")
    (root / "Selected.fwl").write_bytes(b"metadata")
    (root / "Other.db").write_bytes(b"other")
    backups = tmp_path / "backups"
    monkeypatch.setattr(
        "app.services.save_file_service.AppConfig.get_backups_directory",
        lambda: backups,
    )

    backup = SaveFileService.backup_project(
        _project("Selected", root),
        GameId.VALHEIM.value,
    )

    assert {path.name for path in backup.iterdir()} == {"Selected.db", "Selected.fwl"}


def test_flat_valheim_sync_preserves_other_worlds(tmp_path: Path) -> None:
    root = tmp_path / "worlds_local"
    source = tmp_path / "source"
    root.mkdir()
    source.mkdir()
    (root / "Selected.db").write_bytes(b"old")
    (root / "Selected.fwl").write_bytes(b"stale")
    (root / "Other.db").write_bytes(b"other")
    (source / "Selected.db").write_bytes(b"new")

    SaveFileService.synchronize_project(
        _project("Selected", root),
        source,
        GameId.VALHEIM.value,
    )

    assert (root / "Selected.db").read_bytes() == b"new"
    assert not (root / "Selected.fwl").exists()
    assert (root / "Other.db").read_bytes() == b"other"


def test_flat_valheim_sync_rejects_old_multi_world_package(tmp_path: Path) -> None:
    root = tmp_path / "worlds_local"
    source = tmp_path / "source"
    root.mkdir()
    source.mkdir()
    (source / "Selected.db").write_bytes(b"selected")
    (source / "Other.db").write_bytes(b"other")

    with pytest.raises(ValueError, match="contains files from other worlds"):
        SaveFileService.synchronize_project(
            _project("Selected", root),
            source,
            GameId.VALHEIM.value,
        )


def test_chunked_valheim_sync_manages_entire_dedicated_directory(tmp_path: Path) -> None:
    root = tmp_path / "New World"
    source = tmp_path / "source"
    root.mkdir()
    source.mkdir()
    (root / "obsolete.chunk").write_bytes(b"old")
    (source / "_main.8.db2").write_bytes(b"database")
    (source / "_main.8.fwl2").write_bytes(b"metadata")
    (source / "region.chunk").write_bytes(b"region")

    SaveFileService.synchronize_project(
        _project("New World", root),
        source,
        GameId.VALHEIM.value,
    )

    assert not (root / "obsolete.chunk").exists()
    assert (root / "region.chunk").read_bytes() == b"region"


def test_sync_rejects_destination_symlink_that_escapes_project(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    root.mkdir()
    source.mkdir()
    outside.mkdir()
    (source / "linked").mkdir()
    (source / "linked" / "world.sav").write_bytes(b"untrusted")
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks is unavailable on this computer.")

    with pytest.raises(ValueError, match="outside its expected directory"):
        SaveFileService.synchronize_project(_project("World", root), source)

    assert not (outside / "world.sav").exists()
