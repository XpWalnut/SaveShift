from pathlib import Path

from app.database.models.project import Project
from app.database.repositories.project_repository import ProjectRepository
from app.packages.checksum import calculate_sha256
from app.packages.package_extractor import PackageExtractor
from app.packages.package_info import PackageInfo
from app.packages.package_reader import PackageReader
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)
from app.services.save_file_service import SaveFileService


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
            raise NotImplementedError(
                "Importing packages for new/untracked projects is not implemented yet."
            )

        ImportService._validate_import_version(
            package_info=package_info,
            project=project,
        )

        extracted_path = PackageExtractor.extract(package_path)

        backup_path = SaveFileService.backup_project(
            project=project,
            game_id=package_info.game_id,
        )

        SaveFileService.synchronize_project(
            project=project,
            source_directory=extracted_path,
        )

        package_checksum = calculate_sha256(package_path)

        return ProjectVersionService.create_version(
            project_id=project.id,
            created_by=imported_by,
            source_type=ProjectVersionSource.IMPORTED,
            version_number=package_info.project_version,
            package_path=str(package_path),
            backup_path=str(backup_path),
            package_checksum=package_checksum,
            notes=notes,
        )

    @staticmethod
    def validate_import_package(package_path: Path) -> None:
        package_info = PackageReader.read(package_path)
        project = ProjectRepository.get_by_uuid(package_info.project_uuid)

        if project is None:
            raise NotImplementedError(
                "Importing packages for new/untracked projects is not implemented yet."
            )

        ImportService._validate_import_version(
            package_info=package_info,
            project=project,
        )

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