import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.database.models.project import Project
from app.packages.package_metadata import PackageMetadata
from app.packages.package_reader import PackageReader
from app.packages.package_service import PackageService


def _project(root: Path) -> Project:
    return Project(
        id=1,
        installed_game_id=1,
        uuid="12345678-1234-4678-9234-567812345678",
        name="Metadata World",
        local_path=str(root),
    )


def test_package_round_trip_preserves_structured_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "world"
    root.mkdir()
    save_file = root / "world.sav"
    save_file.write_bytes(b"world")
    package_path = tmp_path / "metadata.sspkg"
    metadata = PackageMetadata(
        source_device_name="Alice's PC",
        lineage_name="friends",
        parent_project_version=4,
        parent_package_checksum="a" * 64,
        notes="Defeated the second boss",
        game_metadata={"game_version": "0.4.5f2", "save_slot": 2},
    )

    PackageService.create_package(
        game_id="schedule_i",
        project=_project(root),
        project_version=5,
        root_path=root,
        save_files=[save_file],
        output_path=package_path,
        created_by="Alice",
        metadata=metadata,
    )

    assert PackageReader.read(package_path).metadata == metadata


def test_legacy_package_without_metadata_uses_safe_defaults(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "legacy.sspkg"
    manifest = {
        "package_format_version": 1,
        "project_uuid": "12345678-1234-4678-9234-567812345678",
        "project_version": 1,
        "game_id": "valheim",
        "project_name": "Legacy World",
        "created_at_utc": "2026-07-20T12:00:00+00:00",
        "created_by": "Alice",
        "save_shift_version": "0.1.0-alpha.3",
        "files": [],
    }

    with ZipFile(package_path, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("checksums.json", "{}")

    assert PackageReader.read(
        package_path,
        verify=False,
    ).metadata == PackageMetadata()


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ([], "metadata must be an object"),
        (
            {"parent_project_version": 0},
            "parent_project_version must be a positive integer",
        ),
        (
            {"parent_package_checksum": "not-a-checksum"},
            "parent_package_checksum must be a SHA-256 checksum",
        ),
        (
            {"game_metadata": []},
            "game_metadata must be an object",
        ),
    ],
)
def test_invalid_structured_metadata_is_rejected(
    tmp_path: Path,
    metadata: object,
    message: str,
) -> None:
    package_path = tmp_path / "invalid.sspkg"
    manifest = {
        "package_format_version": 1,
        "project_uuid": "12345678-1234-4678-9234-567812345678",
        "project_version": 2,
        "game_id": "valheim",
        "project_name": "Invalid World",
        "created_at_utc": "2026-07-20T12:00:00+00:00",
        "created_by": "Alice",
        "save_shift_version": "0.1.0-alpha.3",
        "files": [],
        "metadata": metadata,
    }

    with ZipFile(package_path, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("checksums.json", "{}")

    with pytest.raises(ValueError, match=message):
        PackageReader.read(package_path, verify=False)
