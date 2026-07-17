from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.config import AppConfig
from app.database.models.project import Project
from app.database.repositories.installed_game_repository import InstalledGameRepository
from app.database.repositories.project_repository import ProjectRepository
from app.games.game_id import GameId
from app.packages.checksum import calculate_sha256
from app.packages.package_service import PackageService
from app.packages.package_journal_entry import PackageJournalEntry
from app.services.hosting_service import HostingService
from app.services.import_service import ImportService
from app.services.project_service import ProjectService
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)
from app.services.restore_service import RestoreService
from app.services.session_journal_service import SessionJournalService


PROJECT_UUID = "12345678-1234-5678-1234-567812345678"


def _redirect_application_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        AppConfig,
        "get_packages_directory",
        lambda: tmp_path / "app-data" / "packages",
    )
    monkeypatch.setattr(
        AppConfig,
        "get_temp_directory",
        lambda: tmp_path / "app-data" / "temp",
    )
    monkeypatch.setattr(
        AppConfig,
        "get_backups_directory",
        lambda: tmp_path / "app-data" / "backups",
    )


def test_verified_package_import_creates_discovered_project_and_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_application_directories(monkeypatch, tmp_path)

    source_root = tmp_path / "source-world"
    nested_source = source_root / "nested"
    nested_source.mkdir(parents=True)
    world_file = source_root / "world.sav"
    settings_file = nested_source / "settings.ini"
    world_file.write_bytes(b"world-state")
    settings_file.write_text("difficulty=hard", encoding="utf-8")

    package_project = Project(
        installed_game_id=0,
        name="Shared World",
        local_path=str(source_root),
        uuid=PROJECT_UUID,
    )
    package_path = tmp_path / "handoff" / "shared-world.sspkg"
    PackageService.create_package(
        game_id=GameId.ABIOTIC_FACTOR.value,
        project=package_project,
        project_version=7,
        root_path=source_root,
        save_files=[world_file, settings_file],
        output_path=package_path,
        created_by="Original Host",
        journal_entries=(
            PackageJournalEntry.create(
                entry_uuid="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                title="Power restored",
                body="The group brought the facility generators online.",
                created_by="Original Host",
                created_at_utc=datetime(2026, 7, 13, 12, tzinfo=UTC),
                project_version_number=7,
            ),
        ),
    )

    abiotic_save_root = tmp_path / "abiotic-saves"
    steam_user_root = abiotic_save_root / "76561198000000000"
    steam_user_root.mkdir(parents=True)
    installed_game = InstalledGameRepository.add(
        game_id=GameId.ABIOTIC_FACTOR.value,
        display_name="Abiotic Factor",
        save_path=str(abiotic_save_root),
    )

    imported_version = ImportService.import_package(
        package_path=package_path,
        imported_by="Receiving Player",
        notes="Received through integration test",
    )

    imported_project = ProjectRepository.get_by_uuid(PROJECT_UUID)
    assert imported_project is not None
    assert imported_project.installed_game_id == installed_game.id
    assert imported_project.name == "Shared World"

    expected_target = steam_user_root / "Worlds" / "Shared World"
    assert imported_project.local_path == str(expected_target)
    assert (expected_target / "world.sav").read_bytes() == b"world-state"
    assert (
        expected_target / "nested" / "settings.ini"
    ).read_text(encoding="utf-8") == "difficulty=hard"

    assert imported_version.project_id == imported_project.id
    assert imported_version.version_number == 7
    assert imported_version.source_type == ProjectVersionSource.IMPORTED
    assert imported_version.created_by == "Receiving Player"
    assert imported_version.package_checksum == calculate_sha256(package_path)
    assert imported_version.backup_path is None
    assert imported_version.notes == "Received through integration test"

    journal_entries = SessionJournalService.get_entries_for_project(
        imported_project.id
    )
    assert len(journal_entries) == 1
    assert journal_entries[0].entry_uuid == "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    assert journal_entries[0].title == "Power restored"
    assert journal_entries[0].project_version_number == 7


def test_host_modify_and_restore_round_trip_preserves_history_and_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_application_directories(monkeypatch, tmp_path)

    installed_game = InstalledGameRepository.add(
        game_id=GameId.VALHEIM.value,
        display_name="Valheim",
        save_path=str(tmp_path / "valheim-saves"),
    )
    project_root = tmp_path / "valheim-saves" / "worlds_local" / "Regression World"
    project_root.mkdir(parents=True)
    world_file = project_root / "Regression World.db"
    metadata_file = project_root / "Regression World.fwl"
    world_file.write_bytes(b"hosted-world-state")
    metadata_file.write_bytes(b"hosted-world-metadata")

    project = ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid=PROJECT_UUID,
        name="Regression World",
        local_path=project_root,
    )

    hosted_version = HostingService.host_project(
        project_id=project.id,
        game_id=GameId.VALHEIM.value,
        hosted_by="Original Host",
        notes="Known good state",
    )

    assert hosted_version.version_number == 1
    assert hosted_version.source_type == ProjectVersionSource.HOSTED
    assert hosted_version.package_path is not None
    assert Path(hosted_version.package_path).is_file()
    assert hosted_version.package_checksum == calculate_sha256(
        Path(hosted_version.package_path)
    )

    world_file.write_bytes(b"newer-state-before-restore")
    extra_file = project_root / "created-after-hosting.tmp"
    extra_file.write_bytes(b"must be removed by restore")

    restored_version = RestoreService.restore(
        project_version=hosted_version,
        restored_by="Restoring Player",
    )

    assert world_file.read_bytes() == b"hosted-world-state"
    assert metadata_file.read_bytes() == b"hosted-world-metadata"
    assert not extra_file.exists()

    assert restored_version.version_number == 2
    assert restored_version.source_type == ProjectVersionSource.RESTORED
    assert restored_version.created_by == "Restoring Player"
    assert restored_version.parent_version_id == hosted_version.id
    assert restored_version.restored_from_version_id == hosted_version.id
    assert restored_version.lineage_name == hosted_version.lineage_name
    assert restored_version.backup_path is not None

    backup_path = Path(restored_version.backup_path)
    assert (backup_path / world_file.name).read_bytes() == b"newer-state-before-restore"
    assert (backup_path / extra_file.name).read_bytes() == b"must be removed by restore"

    versions = ProjectVersionService.get_versions_for_project(project.id)
    assert [version.version_number for version in versions] == [1, 2]
    assert [version.source_type for version in versions] == [
        ProjectVersionSource.HOSTED,
        ProjectVersionSource.RESTORED,
    ]
