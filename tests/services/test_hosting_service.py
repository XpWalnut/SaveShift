from pathlib import Path

import pytest

from app.database.repositories.installed_game_repository import InstalledGameRepository
from app.database.repositories.project_version_repository import ProjectVersionRepository
from app.games.game_id import GameId
from app.packages.package_service import PackageService
from app.services.hosting_service import HostingService
from app.services.project_service import ProjectService
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)
from app.services.session_journal_service import SessionJournalService


def _create_project(tmp_path: Path, *, create_directory: bool = True):
    installed_game = InstalledGameRepository.add(
        game_id=GameId.VALHEIM.value,
        display_name="Valheim",
        save_path=str(tmp_path / "game-saves"),
    )
    project_path = tmp_path / "projects" / "Regression World"

    if create_directory:
        project_path.mkdir(parents=True)

    return ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid="12345678-1234-5678-1234-567812345678",
        name="Regression World",
        local_path=project_path,
    )


def test_hosting_rejects_missing_project() -> None:
    with pytest.raises(ValueError, match="Project not found: 999"):
        HostingService.host_project(
            project_id=999,
            game_id=GameId.VALHEIM.value,
            hosted_by="Test Host",
        )


def test_hosting_rejects_missing_project_directory(tmp_path: Path) -> None:
    project = _create_project(tmp_path, create_directory=False)

    with pytest.raises(FileNotFoundError, match="Project folder does not exist"):
        HostingService.host_project(
            project_id=project.id,
            game_id=GameId.VALHEIM.value,
            hosted_by="Test Host",
        )


def test_hosting_rejects_project_without_save_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)

    def reject_empty_package(**kwargs: object) -> Path:
        assert kwargs["save_files"] == []
        raise ValueError("Cannot create package without save files.")

    monkeypatch.setattr(
        PackageService,
        "create_project_package",
        reject_empty_package,
    )

    with pytest.raises(ValueError, match="Cannot create package without save files"):
        HostingService.host_project(
            project_id=project.id,
            game_id=GameId.VALHEIM.value,
            hosted_by="Test Host",
        )


def test_hosting_creates_next_version_with_package_checksum_and_notes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    project_root = Path(project.local_path)
    world_file = project_root / "Regression World.db"
    metadata_file = project_root / "Regression World.fwl"
    world_file.write_bytes(b"world")
    metadata_file.write_bytes(b"metadata")
    previous_version = ProjectVersionService.create_version(
        project_id=project.id,
        created_by="Previous Host",
        source_type=ProjectVersionSource.HOSTED,
        version_number=3,
        package_checksum="a" * 64,
        lineage_name="friends",
    )

    package_path = tmp_path / "packages" / "regression.sspkg"
    package_path.parent.mkdir()
    package_path.write_bytes(b"package")
    package_calls: list[dict[str, object]] = []

    def fake_create_package(**kwargs: object) -> Path:
        package_calls.append(kwargs)
        return package_path

    monkeypatch.setattr(
        PackageService,
        "create_project_package",
        fake_create_package,
    )
    monkeypatch.setattr(
        "app.services.hosting_service.calculate_sha256",
        lambda path: "b" * 64 if path == package_path else pytest.fail("wrong path"),
    )
    monkeypatch.setattr(
        HostingService,
        "_get_game_metadata",
        lambda _project, _game_id: {"game_version": "test-version"},
    )

    result = HostingService.host_project(
        project_id=project.id,
        game_id=GameId.VALHEIM.value,
        hosted_by="  Current Host  ",
        notes="Known good version",
        source_device_name="  Gaming PC  ",
    )

    assert len(package_calls) == 1
    assert package_calls[0]["game_id"] == GameId.VALHEIM.value
    assert package_calls[0]["project"].id == project.id
    assert package_calls[0]["project_version"] == 4
    assert set(package_calls[0]["save_files"]) == {world_file, metadata_file}
    assert package_calls[0]["created_by"] == "  Current Host  "
    metadata = package_calls[0]["metadata"]
    assert metadata.source_device_name == "Gaming PC"
    assert metadata.lineage_name == "friends"
    assert metadata.parent_project_version == 3
    assert metadata.parent_package_checksum == "a" * 64
    assert metadata.notes == "Known good version"
    assert metadata.game_metadata == {"game_version": "test-version"}

    recorded = ProjectVersionRepository.get_by_id(result.id)
    assert recorded is not None
    assert recorded.project_id == project.id
    assert recorded.version_number == 4
    assert recorded.created_by == "Current Host"
    assert recorded.source_type == ProjectVersionSource.HOSTED
    assert recorded.package_path == str(package_path)
    assert recorded.package_checksum == "b" * 64
    assert recorded.parent_version_id == previous_version.id
    assert recorded.lineage_name == "friends"
    assert recorded.notes == "Known good version"


def test_hosting_flat_valheim_world_excludes_other_worlds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_root = tmp_path / "worlds_local"
    save_root.mkdir()
    selected_db = save_root / "Selected.db"
    selected_fwl = save_root / "Selected.fwl"
    selected_db.write_bytes(b"selected")
    selected_fwl.write_bytes(b"metadata")
    (save_root / "Other.db").write_bytes(b"other")
    installed_game = InstalledGameRepository.add(
        game_id=GameId.VALHEIM.value,
        display_name="Valheim",
        save_path=str(save_root),
    )
    project = ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid="87654321-4321-8765-4321-876543218765",
        name="Selected",
        local_path=save_root,
    )
    package_path = tmp_path / "packages" / "selected.sspkg"
    package_path.parent.mkdir()
    package_path.write_bytes(b"package")
    package_calls: list[dict[str, object]] = []

    def fake_create_package(**kwargs: object) -> Path:
        package_calls.append(kwargs)
        return package_path

    monkeypatch.setattr(
        PackageService,
        "create_project_package",
        fake_create_package,
    )
    monkeypatch.setattr(
        "app.services.hosting_service.calculate_sha256",
        lambda _path: "d" * 64,
    )

    HostingService.host_project(
        project_id=project.id,
        game_id=GameId.VALHEIM.value,
        hosted_by="Test Host",
    )

    assert set(package_calls[0]["save_files"]) == {
        selected_db,
        selected_fwl,
    }


def test_package_creation_failure_does_not_record_hosted_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    (Path(project.local_path) / "world.sav").write_bytes(b"world")

    def fail_package_creation(**_kwargs: object) -> Path:
        raise RuntimeError("package creation failed")

    monkeypatch.setattr(
        PackageService,
        "create_project_package",
        fail_package_creation,
    )

    with pytest.raises(RuntimeError, match="package creation failed"):
        HostingService.host_project(
            project_id=project.id,
            game_id=GameId.VALHEIM.value,
            hosted_by="Test Host",
        )

    assert ProjectVersionService.get_versions_for_project(project.id) == []


def test_hosting_includes_existing_and_new_journal_entries_in_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path)
    (Path(project.local_path) / "world.sav").write_bytes(b"world")
    existing = SessionJournalService.create_entry(
        project_id=project.id,
        entry_uuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        title="The first night",
        body="We built a shelter before dark.",
        created_by="Alice",
    )
    package_path = tmp_path / "packages" / "journal.sspkg"
    package_path.parent.mkdir()
    package_path.write_bytes(b"package")
    package_calls: list[dict[str, object]] = []

    def fake_create_package(**kwargs: object) -> Path:
        package_calls.append(kwargs)
        return package_path

    monkeypatch.setattr(PackageService, "create_project_package", fake_create_package)
    monkeypatch.setattr(
        "app.services.hosting_service.calculate_sha256",
        lambda _path: "c" * 64,
    )

    version = HostingService.host_project(
        project_id=project.id,
        game_id=GameId.VALHEIM.value,
        hosted_by="Bob",
        journal_title="Boss defeated",
        journal_body="The group defeated the first boss.",
    )

    packaged_entries = package_calls[0]["journal_entries"]
    assert len(packaged_entries) == 2
    assert packaged_entries[0].entry_uuid == existing.entry_uuid
    assert packaged_entries[1].title == "Boss defeated"
    assert packaged_entries[1].project_version_number == version.version_number

    stored_entries = SessionJournalService.get_entries_for_project(project.id)
    assert [entry.title for entry in stored_entries] == [
        "The first night",
        "Boss defeated",
    ]
    assert stored_entries[-1].project_version_number == version.version_number
