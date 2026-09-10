from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.database.repositories.installed_game_repository import InstalledGameRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.project_version_repository import ProjectVersionRepository
from app.games.game_id import GameId
from app.games.project_discovery import ImportTarget
from app.games.registry import GameRegistry
from app.packages.package_extractor import PackageExtractor
from app.packages.package_info import PackageInfo
from app.packages.package_journal_entry import PackageJournalEntry
from app.packages.package_metadata import PackageMetadata
from app.packages.package_reader import PackageReader
from app.services.import_service import ImportService
from app.services.import_conflict import ImportConflictKind
from app.services.project_service import ProjectService
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)
from app.services.save_file_service import SaveFileService
from app.services.session_journal_service import SessionJournalService


PROJECT_UUID = "12345678-1234-5678-1234-567812345678"


def _package_info(
    *,
    project_uuid: str = PROJECT_UUID,
    project_version: int = 2,
    game_id: str = GameId.ABIOTIC_FACTOR.value,
    project_name: str = "Regression Test World",
    journal_entries: tuple[PackageJournalEntry, ...] = (),
    metadata: PackageMetadata | None = None,
) -> PackageInfo:
    return PackageInfo(
        package_format_version=1,
        project_uuid=project_uuid,
        project_version=project_version,
        game_id=game_id,
        project_name=project_name,
        created_at_utc="2026-07-13T12:00:00+00:00",
        created_by="Package Host",
        save_shift_version="0.1.0-alpha.2",
        file_count=2,
        verified=True,
        metadata=metadata or PackageMetadata(),
        journal_entries=journal_entries,
    )


def _create_installed_game(
    save_path: Path,
    *,
    game_id: str = GameId.ABIOTIC_FACTOR.value,
):
    return InstalledGameRepository.add(
        game_id=game_id,
        display_name="Regression Test Game",
        save_path=str(save_path),
    )


def _create_project(
    tmp_path: Path,
    *,
    project_uuid: str = PROJECT_UUID,
    create_directory: bool = True,
) -> Project:
    installed_game = _create_installed_game(tmp_path / "game-saves")
    project_path = tmp_path / "projects" / "regression-world"

    if create_directory:
        project_path.mkdir(parents=True)

    return ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid=project_uuid,
        name="Regression Test World",
        local_path=project_path,
    )


def _create_version(
    project: Project,
    version_number: int,
    package_checksum: str | None = None,
) -> ProjectVersion:
    return ProjectVersionService.create_version(
        project_id=project.id,
        created_by="Local Host",
        source_type=ProjectVersionSource.HOSTED,
        version_number=version_number,
        package_checksum=package_checksum,
    )


def _mock_package_read(
    monkeypatch: pytest.MonkeyPatch,
    package_info: PackageInfo,
) -> None:
    monkeypatch.setattr(
        PackageReader,
        "read",
        lambda _package_path: package_info,
    )


def _mock_import_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    extracted_path: Path,
) -> None:
    monkeypatch.setattr(
        PackageExtractor,
        "extract",
        lambda _package_path: extracted_path,
    )
    monkeypatch.setattr(
        "app.services.import_service.calculate_sha256",
        lambda _package_path: "a" * 64,
    )


def test_newer_package_version_is_allowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    _create_version(project, version_number=2)
    package_path = tmp_path / "incoming.sspkg"
    _mock_package_read(monkeypatch, _package_info(project_version=3))

    analysis = ImportService.analyze_import(package_path)

    assert analysis.kind == ImportConflictKind.UNVERIFIED_NEWER


def test_older_package_version_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    _create_version(project, version_number=3)
    _mock_package_read(monkeypatch, _package_info(project_version=2))

    with pytest.raises(
        ValueError,
        match="The package is older than your current project",
    ):
        ImportService.validate_import_package(tmp_path / "older.sspkg")


def test_group_handoff_can_make_older_version_current_without_erasing_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    version_four = _create_version(project, version_number=4)
    version_five = _create_version(project, version_number=5)
    package_info = _package_info(project_version=3)
    extracted_path = tmp_path / "extracted"
    extracted_path.mkdir()
    _mock_package_read(monkeypatch, package_info)
    _mock_import_boundaries(monkeypatch, extracted_path)
    monkeypatch.setattr(
        SaveFileService,
        "backup_project",
        lambda **_kwargs: tmp_path / "backup",
    )
    monkeypatch.setattr(
        SaveFileService,
        "synchronize_project",
        lambda **_kwargs: None,
    )

    imported = ImportService.import_package(
        package_path=tmp_path / "group-handoff.sspkg",
        imported_by="Receiving Player",
        allow_replace=True,
        allow_group_reconciliation=True,
    )

    assert imported.version_number == 3
    assert ProjectVersionService.get_latest_version(project.id).id == imported.id
    assert {
        version.id
        for version in ProjectVersionService.get_versions_for_project(project.id)
    } == {version_four.id, version_five.id, imported.id}
    assert ProjectVersionService.get_next_version_number(project.id) == 6


def test_duplicate_package_version_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    _create_version(
        project,
        version_number=2,
        package_checksum="a" * 64,
    )
    _mock_package_read(monkeypatch, _package_info(project_version=2))
    monkeypatch.setattr(
        "app.services.import_service.calculate_sha256",
        lambda _package_path: "a" * 64,
    )

    with pytest.raises(
        ValueError,
        match="This package version has already been imported",
    ):
        ImportService.validate_import_package(tmp_path / "duplicate.sspkg")


def test_existing_project_is_backed_up_and_import_version_is_recorded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    parent_version = _create_version(project, version_number=1)
    package_info = _package_info(
        project_version=2,
        metadata=PackageMetadata(
            lineage_name="friends",
            parent_project_version=1,
            notes="Notes carried by package",
        ),
    )
    package_path = tmp_path / "incoming.sspkg"
    extracted_path = tmp_path / "extracted"
    extracted_path.mkdir()
    backup_path = tmp_path / "backups" / "before-import"
    backup_calls: list[dict[str, object]] = []
    synchronize_calls: list[dict[str, object]] = []

    _mock_package_read(monkeypatch, package_info)
    _mock_import_boundaries(monkeypatch, extracted_path)

    def fake_backup_project(**kwargs: object) -> Path:
        backup_calls.append(kwargs)
        return backup_path

    def fake_synchronize_project(**kwargs: object) -> None:
        synchronize_calls.append(kwargs)

    monkeypatch.setattr(SaveFileService, "backup_project", fake_backup_project)
    monkeypatch.setattr(
        SaveFileService,
        "synchronize_project",
        fake_synchronize_project,
    )

    result = ImportService.import_package(
        package_path=package_path,
        imported_by="  Importing Player  ",
        notes="Keep this import note",
    )

    assert len(backup_calls) == 1
    assert backup_calls[0]["project"].id == project.id
    assert backup_calls[0]["game_id"] == GameId.ABIOTIC_FACTOR.value

    assert len(synchronize_calls) == 1
    assert synchronize_calls[0]["project"].id == project.id
    assert synchronize_calls[0]["source_directory"] == extracted_path

    recorded = ProjectVersionRepository.get_by_id(result.id)
    assert recorded is not None
    assert recorded.project_id == project.id
    assert recorded.version_number == 2
    assert recorded.created_by == "Importing Player"
    assert recorded.source_type == ProjectVersionSource.IMPORTED
    assert recorded.package_path == str(package_path)
    assert recorded.backup_path == str(backup_path)
    assert recorded.package_checksum == "a" * 64
    assert recorded.parent_version_id == parent_version.id
    assert recorded.lineage_name == "friends"
    assert recorded.notes == "Keep this import note"


def test_import_preserves_package_notes_when_no_local_note_is_supplied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    _create_version(project, version_number=1)
    extracted_path = tmp_path / "extracted"
    extracted_path.mkdir()
    _mock_package_read(
        monkeypatch,
        _package_info(
            metadata=PackageMetadata(notes="Shared package note"),
        ),
    )
    _mock_import_boundaries(monkeypatch, extracted_path)
    monkeypatch.setattr(
        SaveFileService,
        "backup_project",
        lambda **_kwargs: tmp_path / "backup",
    )
    monkeypatch.setattr(
        SaveFileService,
        "synchronize_project",
        lambda **_kwargs: None,
    )

    imported = ImportService.import_package(
        package_path=tmp_path / "incoming.sspkg",
        imported_by="Receiving Player",
        allow_replace=True,
    )

    assert imported.notes == "Shared package note"


def test_import_does_not_claim_unmatched_package_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    _create_version(project, version_number=1)
    extracted_path = tmp_path / "extracted"
    extracted_path.mkdir()
    _mock_package_read(
        monkeypatch,
        _package_info(
            metadata=PackageMetadata(
                parent_project_version=1,
                parent_package_checksum="b" * 64,
            ),
        ),
    )
    _mock_import_boundaries(monkeypatch, extracted_path)
    monkeypatch.setattr(
        SaveFileService,
        "backup_project",
        lambda **_kwargs: tmp_path / "backup",
    )
    monkeypatch.setattr(
        SaveFileService,
        "synchronize_project",
        lambda **_kwargs: None,
    )

    imported = ImportService.import_package(
        package_path=tmp_path / "incoming.sspkg",
        imported_by="Receiving Player",
        allow_replace=True,
    )

    assert imported.parent_version_id is None


def test_missing_existing_project_directory_skips_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path, create_directory=False)
    package_path = tmp_path / "incoming.sspkg"
    extracted_path = tmp_path / "extracted"
    extracted_path.mkdir()
    _mock_package_read(monkeypatch, _package_info())
    _mock_import_boundaries(monkeypatch, extracted_path)

    def unexpected_backup(**_kwargs: object) -> Path:
        raise AssertionError("backup_project should not be called")

    monkeypatch.setattr(SaveFileService, "backup_project", unexpected_backup)
    monkeypatch.setattr(
        SaveFileService,
        "synchronize_project",
        lambda **_kwargs: None,
    )

    result = ImportService.import_package(
        package_path=package_path,
        imported_by="Importing Player",
        allow_replace=True,
    )

    assert result.project_id == project.id
    assert result.backup_path is None


def test_extracted_files_are_synchronized_into_existing_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    project_path = Path(project.local_path)
    (project_path / "stale.sav").write_text("old", encoding="utf-8")
    (project_path / "changed.sav").write_text("before", encoding="utf-8")

    extracted_path = tmp_path / "extracted"
    (extracted_path / "nested").mkdir(parents=True)
    (extracted_path / "changed.sav").write_text("after", encoding="utf-8")
    (extracted_path / "nested" / "new.sav").write_text("new", encoding="utf-8")

    _mock_package_read(monkeypatch, _package_info())
    _mock_import_boundaries(monkeypatch, extracted_path)
    monkeypatch.setattr(
        SaveFileService,
        "backup_project",
        lambda **_kwargs: tmp_path / "backup",
    )

    ImportService.import_package(
        package_path=tmp_path / "incoming.sspkg",
        imported_by="Importing Player",
        allow_replace=True,
    )

    assert not (project_path / "stale.sav").exists()
    assert (project_path / "changed.sav").read_text(encoding="utf-8") == "after"
    assert (project_path / "nested" / "new.sav").read_text(encoding="utf-8") == "new"


def test_unknown_project_uuid_creates_project_at_game_discovery_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_path = tmp_path / "game-saves"
    installed_game = _create_installed_game(save_path)
    import_target_path = save_path / "discovered-target" / "Regression Test World"
    discovery_calls: list[dict[str, object]] = []

    class FakeDiscovery:
        def get_import_target(
            self,
            save_path: Path,
            project_name: str,
            game_metadata=None,
        ) -> ImportTarget:
            discovery_calls.append(
                {
                    "save_path": save_path,
                    "project_name": project_name,
                    "game_metadata": game_metadata,
                }
            )
            return ImportTarget(project_root=import_target_path)

    supported_game = SimpleNamespace(discovery=lambda: FakeDiscovery())
    monkeypatch.setattr(
        GameRegistry,
        "get_by_game_id",
        lambda _game_id: supported_game,
    )

    package_info = _package_info(project_uuid="87654321-4321-8765-4321-876543218765")
    extracted_path = tmp_path / "extracted"
    extracted_path.mkdir()
    _mock_package_read(monkeypatch, package_info)
    _mock_import_boundaries(monkeypatch, extracted_path)

    result = ImportService.import_package(
        package_path=tmp_path / "incoming.sspkg",
        imported_by="Importing Player",
    )

    created_project = ProjectRepository.get_by_uuid(package_info.project_uuid)
    assert created_project is not None
    assert created_project.installed_game_id == installed_game.id
    assert created_project.name == package_info.project_name
    assert created_project.local_path == str(import_target_path)
    assert import_target_path.is_dir()
    assert result.project_id == created_project.id
    assert discovery_calls == [
        {
            "save_path": save_path,
            "project_name": package_info.project_name,
            "game_metadata": package_info.metadata.game_metadata,
        }
    ]


def test_new_project_import_rejects_missing_installed_game(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_info = _package_info(project_uuid="87654321-4321-8765-4321-876543218765")
    _mock_package_read(monkeypatch, package_info)

    with pytest.raises(
        ValueError,
        match="that game is not configured on this computer",
    ):
        ImportService.import_package(
            package_path=tmp_path / "incoming.sspkg",
            imported_by="Importing Player",
        )

    assert ProjectRepository.get_by_uuid(package_info.project_uuid) is None


def test_new_project_import_rejects_unsupported_game_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsupported_game_id = "unsupported_game"
    _create_installed_game(tmp_path / "game-saves", game_id=unsupported_game_id)
    package_info = _package_info(
        project_uuid="87654321-4321-8765-4321-876543218765",
        game_id=unsupported_game_id,
    )
    _mock_package_read(monkeypatch, package_info)

    with pytest.raises(
        ValueError,
        match="Unsupported game ID: unsupported_game",
    ):
        ImportService.import_package(
            package_path=tmp_path / "incoming.sspkg",
            imported_by="Importing Player",
        )

    assert ProjectRepository.get_by_uuid(package_info.project_uuid) is None


def test_import_stores_package_journal_entries_for_the_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    extracted_path = tmp_path / "extracted"
    extracted_path.mkdir()
    journal_entry = PackageJournalEntry.create(
        entry_uuid="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        title="A narrow escape",
        body="Everyone made it back to the base.",
        created_by="Package Host",
        created_at_utc=datetime(2026, 7, 13, 12, tzinfo=UTC),
        project_version_number=2,
    )
    _mock_package_read(
        monkeypatch,
        _package_info(journal_entries=(journal_entry,)),
    )
    _mock_import_boundaries(monkeypatch, extracted_path)
    monkeypatch.setattr(
        SaveFileService,
        "backup_project",
        lambda **_kwargs: tmp_path / "backup",
    )
    monkeypatch.setattr(
        SaveFileService,
        "synchronize_project",
        lambda **_kwargs: None,
    )

    ImportService.import_package(
        package_path=tmp_path / "incoming.sspkg",
        imported_by="Receiving Player",
        allow_replace=True,
    )

    stored = SessionJournalService.get_entries_for_project(project.id)
    assert len(stored) == 1
    assert stored[0].entry_uuid == journal_entry.entry_uuid
    assert stored[0].title == journal_entry.title
    assert stored[0].body == journal_entry.body
    assert stored[0].created_by == journal_entry.created_by
    assert stored[0].project_version_number == 2
