from pathlib import Path

from app.core.logging import logger
from app.database.models.project import Project
from app.database.repositories.installed_game_repository import (
    InstalledGameRepository,
)
from app.database.repositories.project_repository import ProjectRepository
from app.games.registry import GameRegistry
from app.packages.checksum import calculate_sha256
from app.packages.package_metadata import PackageMetadata
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
        source_device_name: str | None = None,
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
                source_device_name=source_device_name,
            )

    @staticmethod
    def _create_hosted_version(
        project,
        game_id: str,
        hosted_by: str,
        notes: str | None,
        journal_title: str | None,
        journal_body: str | None,
        source_device_name: str | None,
    ):
        save_files = SaveFileService.list_project_files(project, game_id)
        parent_version = ProjectVersionService.get_latest_version(project.id)
        project_version_number = (
            parent_version.version_number + 1
            if parent_version is not None
            else 1
        )

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

        metadata = PackageMetadata(
            source_device_name=(
                source_device_name.strip()
                if source_device_name and source_device_name.strip()
                else None
            ),
            lineage_name=(
                parent_version.lineage_name
                if parent_version is not None
                else "main"
            ),
            parent_project_version=(
                parent_version.version_number
                if parent_version is not None
                else None
            ),
            parent_package_checksum=(
                parent_version.package_checksum
                if parent_version is not None
                else None
            ),
            notes=notes.strip() if notes and notes.strip() else None,
            game_metadata=HostingService._get_game_metadata(
                project,
                game_id,
            ),
        )

        package_path = PackageService.create_project_package(
            game_id=game_id,
            project=project,
            project_version=project_version_number,
            save_files=save_files,
            created_by=hosted_by,
            metadata=metadata,
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
            parent_version_id=(
                parent_version.id
                if parent_version is not None
                else None
            ),
            lineage_name=metadata.lineage_name,
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

    @staticmethod
    def _get_game_metadata(
        project: Project,
        game_id: str,
    ) -> dict[str, object]:
        installed_game = InstalledGameRepository.get_by_id(
            project.installed_game_id
        )
        supported_game = GameRegistry.get_by_game_id(game_id)

        if installed_game is None or supported_game is None:
            return {}

        try:
            discovered_projects = supported_game.discovery().discover_projects(
                Path(installed_game.save_path)
            )
            project_root = Path(project.local_path).resolve(strict=False)

            for discovered in discovered_projects:
                if (
                    discovered.name == project.name
                    and discovered.root_path.resolve(strict=False) == project_root
                ):
                    metadata = dict(discovered.metadata)
                    metadata.pop("steam_user_id", None)
                    metadata.pop("file_count", None)
                    return metadata
        except Exception as error:
            logger.warning(
                "Could not collect package metadata for %s: %s",
                project.name,
                error,
            )

        return {}
