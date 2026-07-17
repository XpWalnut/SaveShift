from pathlib import Path

from app.database.repositories.project_repository import ProjectRepository
from app.packages.checksum import calculate_sha256
from app.packages.package_service import PackageService
from app.services.save_file_service import SaveFileService
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)
from app.coordination.local_lock import ProjectOperationLock
from app.packages.package_journal_entry import PackageJournalEntry
from app.services.session_journal_service import SessionJournalService


class HostingService:
    @staticmethod
    def host_project(
        project_id: int,
        game_id: str,
        hosted_by: str,
        notes: str | None = None,
        journal_title: str | None = None,
        journal_body: str | None = None,
    ):
        project = ProjectRepository.get_by_id(project_id)

        if project is None:
            raise ValueError(f"Project not found: {project_id}")

        with ProjectOperationLock(project.uuid, "hosting it"):
            return HostingService._create_hosted_version(
                project=project,
                game_id=game_id,
                hosted_by=hosted_by,
                notes=notes,
                journal_title=journal_title,
                journal_body=journal_body,
            )

    @staticmethod
    def _create_hosted_version(
        project,
        game_id: str,
        hosted_by: str,
        notes: str | None,
        journal_title: str | None,
        journal_body: str | None,
    ):
        save_files = SaveFileService.list_project_files(project)

        project_version_number = ProjectVersionService.get_next_version_number(project.id)

        pending_journal = None

        if journal_title is not None or journal_body is not None:
            pending_journal = PackageJournalEntry.create(
                title=journal_title or "",
                body=journal_body or "",
                created_by=hosted_by,
                project_version_number=project_version_number,
            )

        journal_entries = list(
            SessionJournalService.package_entries_for_project(project.id)
        )

        if pending_journal is not None:
            journal_entries.append(pending_journal)

        package_path = PackageService.create_project_package(
            game_id=game_id,
            project=project,
            project_version=project_version_number,
            save_files=save_files,
            created_by=hosted_by,
            journal_entries=tuple(journal_entries),
        )

        package_checksum = calculate_sha256(package_path)

        version = ProjectVersionService.create_version(
            project_id=project.id,
            created_by=hosted_by,
            source_type=ProjectVersionSource.HOSTED,
            version_number=project_version_number,
            package_path=str(package_path),
            package_checksum=package_checksum,
            notes=notes,
        )

        if pending_journal is not None:
            SessionJournalService.create_entry(
                project_id=project.id,
                entry_uuid=pending_journal.entry_uuid,
                title=pending_journal.title,
                body=pending_journal.body,
                created_by=pending_journal.created_by,
                created_at_utc=SessionJournalService.parse_package_timestamp(
                    pending_journal.created_at_utc
                ),
                project_version_number=project_version_number,
            )

        return version
