from pathlib import Path

import pytest

from app.database.models.project_version import ProjectVersion
from app.database.repositories.installed_game_repository import InstalledGameRepository
from app.database.repositories.project_repository import ProjectRepository
from app.games.game_id import GameId
from app.packages.package_extractor import PackageExtractor
from app.packages.package_reader import PackageReader
from app.services.project_service import ProjectService
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)
from app.services.restore_service import RestoreService
from app.services.save_file_service import SaveFileService


def _create_project(tmp_path: Path, *, create_directory: bool = True):
    installed_game = InstalledGameRepository.add(
        game_id=GameId.ABIOTIC_FACTOR.value,
        display_name="Abiotic Factor",
        save_path=str(tmp_path / "game-saves"),
    )
    project_path = tmp_path / "projects" / "Regression World"

    if create_directory:
        project_path.mkdir(parents=True)

    project = ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid="12345678-1234-5678-1234-567812345678",
        name="Regression World",
        local_path=project_path,
    )
    return project, installed_game


def _create_version(project_id: int, version_number: int, **kwargs: object):
    return ProjectVersionService.create_version(
        project_id=project_id,
        created_by="Original Host",
        source_type=kwargs.pop("source_type", ProjectVersionSource.HOSTED),
        version_number=version_number,
        **kwargs,
    )


def test_restore_uses_available_package_and_records_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, installed_game = _create_project(tmp_path)
    package_path = tmp_path / "version-1.sspkg"
    package_path.write_bytes(b"package")
    extracted_path = tmp_path / "extracted"
    extracted_path.mkdir()
    source_version = _create_version(
        project.id,
        1,
        package_path=str(package_path),
        lineage_name="friends",
    )
    backup_path = tmp_path / "backups" / "before-restore"
    read_calls: list[Path] = []
    synchronize_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        SaveFileService,
        "backup_project",
        lambda **kwargs: (
            backup_path
            if kwargs["game_id"] == installed_game.game_id
            else pytest.fail("wrong game ID")
        ),
    )
    monkeypatch.setattr(
        PackageReader,
        "read",
        lambda path: read_calls.append(path),
    )
    monkeypatch.setattr(
        PackageExtractor,
        "extract",
        lambda path: extracted_path if path == package_path else pytest.fail("wrong package"),
    )
    monkeypatch.setattr(
        SaveFileService,
        "synchronize_project",
        lambda **kwargs: synchronize_calls.append(kwargs),
    )

    result = RestoreService.restore(source_version, restored_by="  Restoring Player  ")

    assert read_calls == [package_path]
    assert len(synchronize_calls) == 1
    assert synchronize_calls[0]["project"].id == project.id
    assert synchronize_calls[0]["source_directory"] == extracted_path
    assert result.version_number == 2
    assert result.created_by == "Restoring Player"
    assert result.source_type == ProjectVersionSource.RESTORED
    assert result.backup_path == str(backup_path)
    assert result.parent_version_id == source_version.id
    assert result.restored_from_version_id == source_version.id
    assert result.lineage_name == "friends"


def test_restore_falls_back_to_backup_and_skips_backup_for_missing_live_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, _installed_game = _create_project(tmp_path, create_directory=False)
    missing_package = tmp_path / "missing.sspkg"
    source_backup = tmp_path / "source-backup"
    source_backup.mkdir()
    source_version = _create_version(
        project.id,
        1,
        package_path=str(missing_package),
        backup_path=str(source_backup),
    )
    synchronize_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        SaveFileService,
        "backup_project",
        lambda **_kwargs: pytest.fail("backup should be skipped"),
    )
    monkeypatch.setattr(
        SaveFileService,
        "synchronize_project",
        lambda **kwargs: synchronize_calls.append(kwargs),
    )

    result = RestoreService.restore(source_version, restored_by="Restoring Player")

    assert len(synchronize_calls) == 1
    assert synchronize_calls[0]["source_directory"] == source_backup
    assert result.backup_path is None


def test_restoring_restored_version_follows_original_restore_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, _installed_game = _create_project(tmp_path)
    original_backup = tmp_path / "original-source"
    original_backup.mkdir()
    original_version = _create_version(
        project.id,
        1,
        backup_path=str(original_backup),
        lineage_name="branch-a",
    )
    replaced_state_backup = tmp_path / "replaced-state"
    replaced_state_backup.mkdir()
    prior_restore = _create_version(
        project.id,
        2,
        source_type=ProjectVersionSource.RESTORED,
        backup_path=str(replaced_state_backup),
        restored_from_version_id=original_version.id,
        lineage_name="branch-a",
    )
    synchronized_sources: list[Path] = []

    monkeypatch.setattr(
        SaveFileService,
        "backup_project",
        lambda **_kwargs: tmp_path / "current-state-backup",
    )
    monkeypatch.setattr(
        SaveFileService,
        "synchronize_project",
        lambda **kwargs: synchronized_sources.append(kwargs["source_directory"]),
    )

    result = RestoreService.restore(prior_restore, restored_by="Restoring Player")

    assert synchronized_sources == [original_backup]
    assert result.version_number == 3
    assert result.parent_version_id == prior_restore.id
    assert result.restored_from_version_id == prior_restore.id
    assert result.lineage_name == "branch-a"


def test_restore_rejects_missing_project() -> None:
    missing_project_version = ProjectVersion(
        id=42,
        project_id=999,
        version_number=1,
        created_by="Host",
        source_type=ProjectVersionSource.HOSTED,
        lineage_name="main",
    )

    with pytest.raises(ValueError, match="Project not found for version: 42"):
        RestoreService.restore(missing_project_version, restored_by="Player")


def test_restore_rejects_project_without_installed_game(tmp_path: Path) -> None:
    project = ProjectRepository.create(
        installed_game_id=999,
        project_uuid="12345678-1234-5678-1234-567812345678",
        name="Orphaned World",
        local_path=tmp_path / "orphaned-world",
    )
    version = _create_version(project.id, 1)

    with pytest.raises(ValueError, match="Installed game not found for project"):
        RestoreService.restore(version, restored_by="Player")


def test_restore_rejects_version_without_existing_package_or_backup(
    tmp_path: Path,
) -> None:
    project, _installed_game = _create_project(tmp_path, create_directory=False)
    version = _create_version(
        project.id,
        1,
        package_path=str(tmp_path / "missing.sspkg"),
        backup_path=str(tmp_path / "missing-backup"),
    )

    with pytest.raises(FileNotFoundError, match="No restore source found"):
        RestoreService.restore(version, restored_by="Player")
