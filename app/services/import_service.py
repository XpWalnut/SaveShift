from pathlib import Path

from app.database.repositories.project_repository import ProjectRepository
from app.packages.checksum import calculate_sha256
from app.packages.package_extractor import PackageExtractor
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

        latest_version = ProjectVersionService.get_latest_version(project.id)

        if latest_version is not None:
            local_version_number = latest_version.version_number
            incoming_version_number = package_info.project_version

            if incoming_version_number < local_version_number:
                raise ValueError(
                    f"Incoming package version ({incoming_version_number}) is older than "
                    f"the current project version ({local_version_number})."
                )

            if incoming_version_number == local_version_number:
                raise ValueError(
                    f"This package version ({incoming_version_number}) has already been imported."
                )

        if project is None:
            raise NotImplementedError(
                "Importing packages for new/untracked projects is not implemented yet."
            )

        extracted_path = PackageExtractor.extract(package_path)

        backup_path = SaveFileService.backup_project(
            project=project,
            game_id=package_info.game_id,
        )

        SaveFileService.restore_project(
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