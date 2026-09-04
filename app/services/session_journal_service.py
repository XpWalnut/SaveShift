from datetime import UTC, datetime

from app.database.models.session_journal_entry import SessionJournalEntry
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.session_journal_repository import (
    SessionJournalRepository,
)
from app.packages.package_journal_entry import PackageJournalEntry


class SessionJournalService:
    @staticmethod
    def create_entry(
        *,
        project_id: int,
        title: str,
        body: str,
        created_by: str,
        project_version_number: int | None = None,
        entry_uuid: str | None = None,
        created_at_utc: datetime | None = None,
    ) -> SessionJournalEntry:
        if ProjectRepository.get_by_id(project_id) is None:
            raise ValueError(f"Project not found: {project_id}")

        payload = PackageJournalEntry.create(
            title=title,
            body=body,
            created_by=created_by,
            project_version_number=project_version_number,
            entry_uuid=entry_uuid,
            created_at_utc=created_at_utc,
        )
        existing = SessionJournalRepository.get_by_entry_uuid(
            payload.entry_uuid
        )

        if existing is not None:
            if existing.project_id != project_id:
                raise ValueError(
                    "Journal entry UUID already belongs to another project."
                )
            return existing

        return SessionJournalRepository.add(
            SessionJournalEntry(
                entry_uuid=payload.entry_uuid,
                project_id=project_id,
                project_version_number=payload.project_version_number,
                title=payload.title,
                body=payload.body,
                created_by=payload.created_by,
                created_at_utc=_parse_timestamp(payload.created_at_utc),
            )
        )

    @staticmethod
    def import_entries(
        project_id: int,
        entries: tuple[PackageJournalEntry, ...],
    ) -> list[SessionJournalEntry]:
        imported: list[SessionJournalEntry] = []

        for entry in entries:
            existing = SessionJournalRepository.get_by_entry_uuid(
                entry.entry_uuid
            )

            if existing is not None:
                if existing.project_id != project_id:
                    raise ValueError(
                        "Journal entry UUID already belongs to another project."
                    )
                continue

            imported.append(
                SessionJournalService.create_entry(
                    project_id=project_id,
                    entry_uuid=entry.entry_uuid,
                    title=entry.title,
                    body=entry.body,
                    created_by=entry.created_by,
                    created_at_utc=_parse_timestamp(entry.created_at_utc),
                    project_version_number=entry.project_version_number,
                )
            )

        return imported

    @staticmethod
    def get_entries_for_project(project_id: int) -> list[SessionJournalEntry]:
        return SessionJournalRepository.get_by_project(project_id)

    @staticmethod
    def get_latest_entry(project_id: int) -> SessionJournalEntry | None:
        return SessionJournalRepository.get_latest(project_id)

    @staticmethod
    def package_entries_for_project(
        project_id: int,
    ) -> tuple[PackageJournalEntry, ...]:
        return tuple(
            PackageJournalEntry.create(
                entry_uuid=entry.entry_uuid,
                title=entry.title,
                body=entry.body,
                created_by=entry.created_by,
                created_at_utc=_as_utc(entry.created_at_utc),
                project_version_number=entry.project_version_number,
            )
            for entry in SessionJournalRepository.get_by_project(project_id)
        )

    @staticmethod
    def parse_package_timestamp(value: str) -> datetime:
        return _parse_timestamp(value)


def _parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None:
        raise ValueError("Journal timestamp must include a UTC offset.")

    return parsed.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)
