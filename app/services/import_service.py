from pathlib import Path

from app.database.models.project import Project
from app.database.repositories.project_repository import ProjectRepository
from app.packages.checksum import calculate_sha256
from app.packages.package_extractor import PackageExtractor
from app.packages.package_info import PackageInfo
from app.packages.package_reader import PackageReader
from app.database.repositories.installed_game_repository import InstalledGameRepository
from app.games.registry import GameRegistry
from app.services.save_file_service import SaveFileService
from app.services.project_service import ProjectService
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)
from app.coordination.local_lock import ProjectOperationLock
from app.services.session_journal_service import SessionJournalService


class ImportService:
    @staticmethod
    def import_package(
        package_path: Path,
        imported_by: str,
        notes: str | None = None,
    ):
        package_info = PackageReader.read(package_path)

        project = ProjectRepository.get_by_uuid(package_info.project_uuid)

        if project is None:
            project = ImportService._create_project_from_package(package_info)

        ImportService._validate_import_version(
            package_info=package_info,
            project=project,
        )

        with ProjectOperationLock(project.uuid, "importing into it"):
            return ImportService._synchronize_package(
                package_path=package_path,
                package_info=package_info,
                project=project,
                imported_by=imported_by,
                notes=notes,
            )

    @staticmethod
    def _synchronize_package(
        package_path: Path,
        package_info: PackageInfo,
        project: Project,
        imported_by: str,
        notes: str | None,
    ):
        extracted_path = PackageExtractor.extract(package_path)

        project_root = Path(project.local_path)

        backup_path = None

        if project_root.exists():
            backup_path = SaveFileService.backup_project(
                project=project,
                game_id=package_info.game_id,
            )

        SaveFileService.synchronize_project(
            project=project,
            source_directory=extracted_path,
        )

        package_checksum = calculate_sha256(package_path)

        version = ProjectVersionService.create_version(
            project_id=project.id,
            created_by=imported_by,
            source_type=ProjectVersionSource.IMPORTED,
            version_number=package_info.project_version,
            package_path=str(package_path),
            backup_path=str(backup_path) if backup_path is not None else None,
            package_checksum=package_checksum,
            notes=notes,
        )

        SessionJournalService.import_entries(
            project.id,
            package_info.journal_entries,
        )

        return version

    @staticmethod
    def validate_import_package(package_path: Path) -> PackageInfo:
        package_info = PackageReader.read(package_path)
        project = ProjectRepository.get_by_uuid(package_info.project_uuid)

        if project is None:
            return package_info

        ImportService._validate_import_version(
            package_info=package_info,
            project=project,
        )

        return package_info

    @staticmethod
    def _validate_import_version(
        package_info: PackageInfo,
        project: Project,
    ) -> None:
        latest_version = ProjectVersionService.get_latest_version(project.id)

        if latest_version is None:
            return

        local_version_number = latest_version.version_number
        incoming_version_number = package_info.project_version

        if incoming_version_number < local_version_number:
            raise ValueError(
                f"The package is older than your current project.\n\n"
                f"Current version: {local_version_number}\n"
                f"Package version: {incoming_version_number}\n\n"
                f"Importing it would overwrite newer progress."
            )

        if incoming_version_number == local_version_number:
            raise ValueError(
                "This package version has already been imported.\n\n"
                f"Current version: {local_version_number}\n"
                f"Package version: {incoming_version_number}"
            )

    @staticmethod
    def _create_project_from_package(package_info: PackageInfo) -> Project:
        installed_game = InstalledGameRepository.get_by_game_id(package_info.game_id)

        if installed_game is None:
            raise ValueError(
                f"This package is for {package_info.game_id}, but that game is not configured on this computer."
            )

        supported_game = GameRegistry.get_by_game_id(package_info.game_id)

        if supported_game is None:
            raise ValueError(f"Unsupported game ID: {package_info.game_id}")


        import_target = supported_game.discovery().get_import_target(
            save_path=Path(installed_game.save_path),
            project_name=package_info.project_name,
        )

        return ProjectService.create_project(
            installed_game_id=installed_game.id,
            project_uuid=package_info.project_uuid,
            name=package_info.project_name,
            local_path=import_target.project_root,
        )
