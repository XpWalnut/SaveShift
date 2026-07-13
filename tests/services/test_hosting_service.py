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
    ProjectVersionService.create_version(
        project_id=project.id,
        created_by="Previous Host",
        source_type=ProjectVersionSource.HOSTED,
        version_number=3,
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

    result = HostingService.host_project(
        project_id=project.id,
        game_id=GameId.VALHEIM.value,
        hosted_by="  Current Host  ",
        notes="Known good version",
    )

    assert len(package_calls) == 1
    assert package_calls[0]["game_id"] == GameId.VALHEIM.value
    assert package_calls[0]["project"].id == project.id
    assert package_calls[0]["project_version"] == 4
    assert set(package_calls[0]["save_files"]) == {world_file, metadata_file}
    assert package_calls[0]["created_by"] == "  Current Host  "

    recorded = ProjectVersionRepository.get_by_id(result.id)
    assert recorded is not None
    assert recorded.project_id == project.id
    assert recorded.version_number == 4
    assert recorded.created_by == "Current Host"
    assert recorded.source_type == ProjectVersionSource.HOSTED
    assert recorded.package_path == str(package_path)
    assert recorded.package_checksum == "b" * 64
    assert recorded.notes == "Known good version"


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
