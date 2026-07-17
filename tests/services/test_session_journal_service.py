from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.database.repositories.installed_game_repository import (
    InstalledGameRepository,
)
from app.packages.package_journal_entry import PackageJournalEntry
from app.services.project_service import ProjectService
from app.services.session_journal_service import SessionJournalService


def _project(tmp_path: Path):
    installed_game = InstalledGameRepository.add(
        game_id="valheim",
        display_name="Valheim",
        save_path=str(tmp_path / "saves"),
    )
    return ProjectService.create_project(
        installed_game_id=installed_game.id,
        project_uuid="6b838790-71b8-4e77-8a64-0a7934056ec3",
        name="Journal World",
        local_path=tmp_path / "saves" / "Journal World",
    )


def test_create_entry_normalizes_and_returns_latest(tmp_path: Path) -> None:
    project = _project(tmp_path)
    first_time = datetime(2026, 7, 15, 12, tzinfo=UTC)
    second_time = first_time + timedelta(hours=2)

    first = SessionJournalService.create_entry(
        project_id=project.id,
        title="  First shelter  ",
        body="  We survived the night.  ",
        created_by="  Alice  ",
        created_at_utc=first_time,
        project_version_number=1,
    )
    second = SessionJournalService.create_entry(
        project_id=project.id,
        title="Portal hub",
        body="Connected the mountain base.",
        created_by="Bob",
        created_at_utc=second_time,
        project_version_number=2,
    )

    assert first.title == "First shelter"
    assert first.body == "We survived the night."
    assert first.created_by == "Alice"
    stored = SessionJournalService.get_entries_for_project(project.id)
    assert [entry.id for entry in stored] == [first.id, second.id]
    assert SessionJournalService.get_latest_entry(project.id).id == second.id


def test_create_entry_validates_project_and_content(tmp_path: Path) -> None:
    project = _project(tmp_path)

    with pytest.raises(ValueError, match="Project not found"):
        SessionJournalService.create_entry(
            project_id=999,
            title="Missing",
            body="Missing project",
            created_by="Alice",
        )

    with pytest.raises(ValueError, match="Journal title is required"):
        SessionJournalService.create_entry(
            project_id=project.id,
            title=" ",
            body="Something happened",
            created_by="Alice",
        )

    with pytest.raises(ValueError, match="cannot exceed 5000"):
        SessionJournalService.create_entry(
            project_id=project.id,
            title="Too much",
            body="x" * 5001,
            created_by="Alice",
        )


def test_import_entries_is_idempotent(tmp_path: Path) -> None:
    project = _project(tmp_path)
    entry = PackageJournalEntry.create(
        entry_uuid="1365d676-7cc6-48d1-9179-18299ad902e0",
        title="The Elder",
        body="Defeated the first boss.",
        created_by="Alice",
        created_at_utc=datetime(2026, 7, 15, 12, tzinfo=UTC),
        project_version_number=3,
    )

    first_import = SessionJournalService.import_entries(project.id, (entry,))
    second_import = SessionJournalService.import_entries(project.id, (entry,))

    assert len(first_import) == 1
    assert second_import == []
    assert len(SessionJournalService.get_entries_for_project(project.id)) == 1


def test_package_entries_preserve_identity_and_version(tmp_path: Path) -> None:
    project = _project(tmp_path)
    created_at = datetime(2026, 7, 15, 12, tzinfo=UTC)
    entry = SessionJournalService.create_entry(
        project_id=project.id,
        entry_uuid="73e6ad65-3383-4dbb-bac7-f90466bafbc4",
        title="New biome",
        body="Found the plains.",
        created_by="Alice",
        created_at_utc=created_at,
        project_version_number=4,
    )

    packaged = SessionJournalService.package_entries_for_project(project.id)

    assert len(packaged) == 1
    assert packaged[0].entry_uuid == entry.entry_uuid
    assert packaged[0].title == entry.title
    assert packaged[0].project_version_number == 4
    assert packaged[0].created_at_utc == created_at.isoformat()
