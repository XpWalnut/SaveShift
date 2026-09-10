from pathlib import Path
import json

import pytest

from app.database.repositories.installed_game_repository import (
    InstalledGameRepository,
)
from app.database.repositories.project_repository import ProjectRepository
from app.games.game_id import GameId
from app.packages.package_info import PackageInfo
from app.packages.package_metadata import PackageMetadata
from app.packages.package_reader import PackageReader
from app.services.import_conflict import ImportConflictKind
from app.services.import_service import ImportService
from app.services.project_service import ProjectService
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)


PROJECT_UUID = "12345678-1234-4678-9234-567812345678"


def _package_info(
    *,
    version: int = 5,
    metadata: PackageMetadata | None = None,
    project_uuid: str = PROJECT_UUID,
) -> PackageInfo:
    return PackageInfo(
        package_format_version=1,
        project_uuid=project_uuid,
        project_version=version,
        game_id=GameId.SCHEDULE_I.value,
        project_name="Conflict Test Empire",
        created_at_utc="2026-07-21T12:00:00+00:00",
        created_by="Alice",
        save_shift_version="0.1.0-alpha.3",
        file_count=20,
        verified=True,
        metadata=metadata or PackageMetadata(),
    )


def _flat_valheim_package_info(
    *,
    project_name: str = "Incoming World",
    project_uuid: str = "87654321-4321-4678-9234-567812345678",
) -> PackageInfo:
    return PackageInfo(
        package_format_version=1,
        project_uuid=project_uuid,
        project_version=1,
        game_id=GameId.VALHEIM.value,
        project_name=project_name,
        created_at_utc="2026-09-10T12:00:00+00:00",
        created_by="Alice",
        save_shift_version="0.1.0-alpha.3",
        file_count=2,
        verified=True,
        metadata=PackageMetadata(
            game_metadata={"storage_layout": "flat"},
        ),
    )


def _create_project(tmp_path: Path):
    installed_game = InstalledGameRepository.add(
        game_id=GameId.SCHEDULE_I.value,
        display_name="Schedule I",
        save_path=str(tmp_path / "saves"),
    )
    project_root = tmp_path / "saves" / "user" / "SaveGame_1"
    project_root.mkdir(parents=True)
    return ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid=PROJECT_UUID,
        name="Conflict Test Empire",
        local_path=project_root,
    )


def _create_version(
    project_id: int,
    *,
    version: int = 4,
    checksum: str = "a" * 64,
):
    return ProjectVersionService.create_version(
        project_id=project_id,
        created_by="Bob",
        source_type=ProjectVersionSource.HOSTED,
        version_number=version,
        package_checksum=checksum,
    )


def _mock_package(
    monkeypatch: pytest.MonkeyPatch,
    package_info: PackageInfo,
) -> None:
    monkeypatch.setattr(
        PackageReader,
        "read",
        lambda _package_path: package_info,
    )


def test_unknown_project_is_classified_as_new(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_root = tmp_path / "saves"
    (save_root / "76561198000000000").mkdir(parents=True)
    InstalledGameRepository.add(
        game_id=GameId.SCHEDULE_I.value,
        display_name="Schedule I",
        save_path=str(save_root),
    )
    _mock_package(
        monkeypatch,
        _package_info(project_uuid="87654321-4321-4678-9234-567812345678"),
    )

    analysis = ImportService.analyze_import(tmp_path / "new.sspkg")

    assert analysis.kind == ImportConflictKind.NEW_PROJECT
    assert not analysis.is_blocked
    assert not analysis.requires_replace_confirmation


def test_unknown_uuid_targeting_existing_files_requires_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_root = tmp_path / "saves"
    save_folder = save_root / "76561198000000000" / "SaveGame_1"
    save_folder.mkdir(parents=True)
    (save_folder / "Game.json").write_text(
        json.dumps({"OrganisationName": "Conflict Test Empire"}),
        encoding="utf-8",
    )
    InstalledGameRepository.add(
        game_id=GameId.SCHEDULE_I.value,
        display_name="Schedule I",
        save_path=str(save_root),
    )
    _mock_package(
        monkeypatch,
        _package_info(project_uuid="87654321-4321-4678-9234-567812345678"),
    )

    analysis = ImportService.analyze_import(tmp_path / "incoming.sspkg")

    assert analysis.kind == ImportConflictKind.NEW_PROJECT_REPLACE_EXISTING
    assert analysis.import_target == save_folder
    assert analysis.requires_replace_confirmation


def test_flat_valheim_import_ignores_other_projects_in_shared_save_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_root = tmp_path / "worlds_local"
    save_root.mkdir()
    (save_root / "Other World.db").write_bytes(b"other")
    installed_game = InstalledGameRepository.add(
        game_id=GameId.VALHEIM.value,
        display_name="Valheim",
        save_path=str(save_root),
    )
    ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        name="Other World",
        local_path=save_root,
    )
    _mock_package(monkeypatch, _flat_valheim_package_info())

    analysis = ImportService.analyze_import(tmp_path / "incoming.sspkg")

    assert analysis.kind == ImportConflictKind.NEW_PROJECT
    assert analysis.target_project is None
    assert not analysis.requires_replace_confirmation


def test_flat_valheim_import_adopts_matching_world_in_shared_save_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_root = tmp_path / "worlds_local"
    save_root.mkdir()
    (save_root / "Incoming World.db").write_bytes(b"local")
    (save_root / "Other World.db").write_bytes(b"other")
    installed_game = InstalledGameRepository.add(
        game_id=GameId.VALHEIM.value,
        display_name="Valheim",
        save_path=str(save_root),
    )
    ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        name="Other World",
        local_path=save_root,
    )
    matching_project = ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        name="Incoming World",
        local_path=save_root,
    )
    _mock_package(monkeypatch, _flat_valheim_package_info())

    analysis = ImportService.analyze_import(tmp_path / "incoming.sspkg")

    assert analysis.kind == ImportConflictKind.ADOPT_EXISTING_PROJECT
    assert analysis.target_project is not None
    assert analysis.target_project.id == matching_project.id
    assert analysis.requires_replace_confirmation


def test_unversioned_local_project_is_adopted_without_duplicate_card(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_root = tmp_path / "saves"
    save_folder = save_root / "76561198000000000" / "SaveGame_1"
    save_folder.mkdir(parents=True)
    (save_folder / "Game.json").write_text(
        json.dumps({"OrganisationName": "Conflict Test Empire"}),
        encoding="utf-8",
    )
    installed_game = InstalledGameRepository.add(
        game_id=GameId.SCHEDULE_I.value,
        display_name="Schedule I",
        save_path=str(save_root),
    )
    local_uuid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    local_project = ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid=local_uuid,
        name="Conflict Test Empire",
        local_path=save_folder,
    )
    package_info = _package_info(
        project_uuid="87654321-4321-4678-9234-567812345678"
    )
    _mock_package(monkeypatch, package_info)
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    monkeypatch.setattr(
        "app.services.import_service.PackageExtractor.extract",
        lambda _package_path: extracted,
    )
    monkeypatch.setattr(
        "app.services.import_service.SaveFileService.backup_project",
        lambda **_kwargs: tmp_path / "backup",
    )
    monkeypatch.setattr(
        "app.services.import_service.SaveFileService.synchronize_project",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.import_service.calculate_sha256",
        lambda _package_path: "c" * 64,
    )

    analysis = ImportService.analyze_import(tmp_path / "incoming.sspkg")
    imported = ImportService.import_package(
        package_path=tmp_path / "incoming.sspkg",
        imported_by="Bob",
        allow_replace=True,
    )

    assert analysis.kind == ImportConflictKind.ADOPT_EXISTING_PROJECT
    assert analysis.target_project is not None
    assert analysis.target_project.id == local_project.id
    adopted = ProjectRepository.get_by_uuid(package_info.project_uuid)
    assert adopted is not None
    assert adopted.id == local_project.id
    assert ProjectRepository.get_by_uuid(local_uuid) is None
    assert len(ProjectRepository.get_all()) == 1
    assert imported.project_id == local_project.id


def test_different_project_identity_with_history_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_root = tmp_path / "saves"
    save_folder = save_root / "76561198000000000" / "SaveGame_1"
    save_folder.mkdir(parents=True)
    (save_folder / "Game.json").write_text(
        json.dumps({"OrganisationName": "Conflict Test Empire"}),
        encoding="utf-8",
    )
    installed_game = InstalledGameRepository.add(
        game_id=GameId.SCHEDULE_I.value,
        display_name="Schedule I",
        save_path=str(save_root),
    )
    local_project = ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        name="Conflict Test Empire",
        local_path=save_folder,
    )
    _create_version(local_project.id)
    _mock_package(
        monkeypatch,
        _package_info(project_uuid="87654321-4321-4678-9234-567812345678"),
    )

    analysis = ImportService.analyze_import(tmp_path / "incoming.sspkg")

    assert analysis.kind == ImportConflictKind.IDENTITY_COLLISION
    assert analysis.is_blocked

    with pytest.raises(ValueError, match="differently identified project"):
        ImportService.import_package(
            package_path=tmp_path / "incoming.sspkg",
            imported_by="Bob",
            allow_replace=True,
        )


def test_existing_project_without_history_requires_backup_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_project(tmp_path)
    _mock_package(monkeypatch, _package_info())

    analysis = ImportService.analyze_import(tmp_path / "incoming.sspkg")

    assert analysis.kind == ImportConflictKind.REPLACE_UNVERSIONED
    assert analysis.requires_replace_confirmation


def test_matching_parent_is_verified_fast_forward(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    _create_version(project.id)
    _mock_package(
        monkeypatch,
        _package_info(
            metadata=PackageMetadata(
                parent_project_version=4,
                parent_package_checksum="a" * 64,
            )
        ),
    )

    analysis = ImportService.analyze_import(tmp_path / "incoming.sspkg")

    assert analysis.kind == ImportConflictKind.FAST_FORWARD
    assert not analysis.requires_replace_confirmation


@pytest.mark.parametrize(
    ("metadata", "expected_kind"),
    [
        (PackageMetadata(), ImportConflictKind.UNVERIFIED_NEWER),
        (
            PackageMetadata(
                parent_project_version=6,
                parent_package_checksum="b" * 64,
            ),
            ImportConflictKind.UNVERIFIED_NEWER,
        ),
        (
            PackageMetadata(
                parent_project_version=4,
                parent_package_checksum="b" * 64,
            ),
            ImportConflictKind.DIVERGED,
        ),
    ],
)
def test_unverified_or_diverged_newer_package_requires_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata: PackageMetadata,
    expected_kind: ImportConflictKind,
) -> None:
    project = _create_project(tmp_path)
    _create_version(project.id)
    _mock_package(monkeypatch, _package_info(metadata=metadata))

    analysis = ImportService.analyze_import(tmp_path / "incoming.sspkg")

    assert analysis.kind == expected_kind
    assert analysis.requires_replace_confirmation


def test_older_package_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    _create_version(project.id, version=6)
    _mock_package(monkeypatch, _package_info(version=5))

    analysis = ImportService.analyze_import(tmp_path / "older.sspkg")

    assert analysis.kind == ImportConflictKind.OLDER
    assert analysis.is_blocked


@pytest.mark.parametrize(
    ("incoming_checksum", "expected_kind"),
    [
        ("a" * 64, ImportConflictKind.DUPLICATE),
        ("b" * 64, ImportConflictKind.VERSION_COLLISION),
    ],
)
def test_same_version_uses_checksum_to_distinguish_duplicate_and_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    incoming_checksum: str,
    expected_kind: ImportConflictKind,
) -> None:
    project = _create_project(tmp_path)
    _create_version(project.id, version=5)
    _mock_package(monkeypatch, _package_info(version=5))
    monkeypatch.setattr(
        "app.services.import_service.calculate_sha256",
        lambda _package_path: incoming_checksum,
    )

    analysis = ImportService.analyze_import(tmp_path / "same-version.sspkg")

    assert analysis.kind == expected_kind
    assert analysis.is_blocked


def test_risky_import_cannot_modify_files_without_explicit_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    _create_version(project.id)
    _mock_package(monkeypatch, _package_info())
    monkeypatch.setattr(
        "app.services.import_service.PackageExtractor.extract",
        lambda _package_path: pytest.fail("package must not be extracted"),
    )

    with pytest.raises(ValueError, match="requires explicit confirmation"):
        ImportService.import_package(
            package_path=tmp_path / "unverified.sspkg",
            imported_by="Bob",
        )
