from pathlib import Path

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.database.repositories.project_repository import ProjectRepository
from app.packages.package_extractor import PackageExtractor
from app.packages.package_reader import PackageReader
from app.services.save_file_service import SaveFileService


class RestoreService:
    @staticmethod
    def restore(project_version: ProjectVersion) -> None:
        project = RestoreService._get_project(project_version)
        restore_directory = RestoreService._get_restore_directory(project_version)

        SaveFileService.synchronize_project(
            project=project,
            source_directory=restore_directory,
        )

    @staticmethod
    def _get_project(project_version: ProjectVersion) -> Project:
        project = ProjectRepository.get_by_id(project_version.project_id)

        if project is None:
            raise ValueError(
                f"Project not found for version: {project_version.id}"
            )

        return project

    @staticmethod
    def _get_restore_directory(project_version: ProjectVersion) -> Path:
        package_path = (
            Path(project_version.package_path)
            if project_version.package_path
            else None
        )

        if package_path is not None and package_path.exists():
            return RestoreService._restore_directory_from_package(package_path)

        backup_path = (
            Path(project_version.backup_path)
            if project_version.backup_path
            else None
        )

        if backup_path is not None and backup_path.exists():
            return RestoreService._restore_directory_from_backup(backup_path)

        raise FileNotFoundError(
            "No restore source found. "
            "The package and backup for this version are missing."
        )

    @staticmethod
    def _restore_directory_from_package(package_path: Path) -> Path:
        PackageReader.read(package_path)
        return PackageExtractor.extract(package_path)

    @staticmethod
    def _restore_directory_from_backup(backup_path: Path) -> Path:
        return backup_path