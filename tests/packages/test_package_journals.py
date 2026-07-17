from datetime import UTC, datetime
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.database.models.project import Project
from app.packages.package_journal_entry import PackageJournalEntry
from app.packages.package_reader import PackageReader
from app.packages.package_service import PackageService


def _project(root: Path) -> Project:
    return Project(
        id=1,
        installed_game_id=1,
        uuid="d0b09d8b-34ca-4be1-bbbe-096105b1dde4",
        name="Package Journal World",
        local_path=str(root),
    )


def test_package_round_trip_preserves_journal_entries(tmp_path: Path) -> None:
    root = tmp_path / "world"
    root.mkdir()
    save_file = root / "world.sav"
    save_file.write_bytes(b"world")
    package_path = tmp_path / "journal.sspkg"
    entry = PackageJournalEntry.create(
        entry_uuid="ff50d89d-8df6-487c-a5ec-e7f67dbf5944",
        title="First voyage",
        body="Reached the edge of the map.",
        created_by="Alice",
        created_at_utc=datetime(2026, 7, 15, 12, tzinfo=UTC),
        project_version_number=2,
    )

    PackageService.create_package(
        game_id="valheim",
        project=_project(root),
        project_version=2,
        root_path=root,
        save_files=[save_file],
        output_path=package_path,
        created_by="Alice",
        journal_entries=(entry,),
    )

    info = PackageReader.read(package_path)

    assert info.journal_entries == (entry,)


def test_legacy_package_without_journal_entries_remains_readable(
    tmp_path: Path,
) -> None:
    package_path = tmp_path / "legacy.sspkg"
    manifest = {
        "package_format_version": 1,
        "project_uuid": "d0b09d8b-34ca-4be1-bbbe-096105b1dde4",
        "project_version": 1,
        "game_id": "valheim",
        "project_name": "Legacy World",
        "created_at_utc": "2026-07-13T12:00:00+00:00",
        "created_by": "Alice",
        "save_shift_version": "0.1.0-alpha.3",
        "files": [],
        "metadata": {},
    }

    with ZipFile(package_path, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("checksums.json", "{}")

    info = PackageReader.read(package_path, verify=False)

    assert info.journal_entries == ()


def test_malformed_journal_metadata_is_rejected(tmp_path: Path) -> None:
    package_path = tmp_path / "invalid.sspkg"
    manifest = {
        "package_format_version": 1,
        "project_uuid": "d0b09d8b-34ca-4be1-bbbe-096105b1dde4",
        "project_version": 1,
        "game_id": "valheim",
        "project_name": "Invalid World",
        "created_at_utc": "2026-07-13T12:00:00+00:00",
        "created_by": "Alice",
        "save_shift_version": "0.1.0-alpha.3",
        "files": [],
        "metadata": {},
        "journal_entries": [{"title": "Missing fields"}],
    }

    with ZipFile(package_path, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("checksums.json", "{}")

    with pytest.raises(ValueError, match="Journal timestamp is missing"):
        PackageReader.read(package_path, verify=False)
