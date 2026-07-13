from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.services.export_service import ExportService
from app.services.hosting_service import HostingService


def _create_project(local_path: Path) -> Project:
    return Project(
        id=1,
        installed_game_id=1,
        name="Regression Test World",
        local_path=str(local_path),
        uuid="12345678-1234-5678-1234-567812345678",
    )


def _create_version(package_path: str | None) -> ProjectVersion:
    return ProjectVersion(
        id=1,
        project_id=1,
        version_number=1,
        created_at_utc=datetime.now(timezone.utc).replace(tzinfo=None),
        created_by="Test Host",
        source_type="hosted",
        package_path=package_path,
        backup_path=None,
        package_checksum=None,
        parent_version_id=None,
        restored_from_version_id=None,
        lineage_name="main",
        notes="Exported manually from Save Shift",
    )


def test_export_project_copies_generated_package_and_returns_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path / "project")

    generated_package = tmp_path / "generated" / "world.sspkg"
    generated_package.parent.mkdir()
    generated_package.write_bytes(b"save-shift-package")

    version = _create_version(str(generated_package))
    host_calls: list[dict[str, object]] = []

    def fake_host_project(**kwargs: object) -> ProjectVersion:
        host_calls.append(kwargs)
        return version

    monkeypatch.setattr(
        HostingService,
        "host_project",
        fake_host_project,
    )

    destination = tmp_path / "exports" / "shared-world.sspkg"

    result = ExportService.export_project(
        project=project,
        game_id="abiotic_factor",
        exported_by="Test Host",
        destination_path=destination,
    )

    assert result is version
    assert destination.read_bytes() == generated_package.read_bytes()

    assert host_calls == [
        {
            "project_id": project.id,
            "game_id": "abiotic_factor",
            "hosted_by": "Test Host",
            "notes": "Exported manually from Save Shift",
        }
    ]


def test_export_project_rejects_version_without_package_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path / "project")
    version = _create_version(None)

    monkeypatch.setattr(
        HostingService,
        "host_project",
        lambda **_kwargs: version,
    )

    with pytest.raises(
        RuntimeError,
        match="created the version but no package path was recorded",
    ):
        ExportService.export_project(
            project=project,
            game_id="abiotic_factor",
            exported_by="Test Host",
            destination_path=tmp_path / "export.sspkg",
        )


def test_export_project_rejects_missing_generated_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _create_project(tmp_path / "project")

    missing_package = tmp_path / "missing" / "world.sspkg"
    version = _create_version(str(missing_package))

    monkeypatch.setattr(
        HostingService,
        "host_project",
        lambda **_kwargs: version,
    )

    with pytest.raises(
        FileNotFoundError,
        match="The generated package could not be found",
    ):
        ExportService.export_project(
            project=project,
            game_id="abiotic_factor",
            exported_by="Test Host",
            destination_path=tmp_path / "export.sspkg",
        )