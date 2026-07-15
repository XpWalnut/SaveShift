from pathlib import Path

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.database.repositories.installed_game_repository import (
    InstalledGameRepository,
)
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.project_version_repository import ProjectVersionRepository
from app.packages.package_extractor import PackageExtractor
from app.packages.package_reader import PackageReader
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)
from app.services.save_file_service import SaveFileService
from app.coordination.local_lock import ProjectOperationLock


class RestoreService:
    @staticmethod
    def restore(
        project_version: ProjectVersion,
        restored_by: str,
    ) -> ProjectVersion:
        project = RestoreService._get_project(project_version)

        with ProjectOperationLock(project.uuid, "restoring it"):
            return RestoreService._restore_project(
                project=project,
                project_version=project_version,
                restored_by=restored_by,
            )

    @staticmethod
    def _restore_project(
        project: Project,
        project_version: ProjectVersion,
        restored_by: str,
    ) -> ProjectVersion:
        installed_game = InstalledGameRepository.get_by_id(
            project.installed_game_id
        )

        if installed_game is None:
            raise ValueError(
                f"Installed game not found for project: {project.name}"
            )

        latest_version = ProjectVersionService.get_latest_version(project.id)

        project_root = Path(project.local_path)
        backup_path: Path | None = None

        if project_root.exists():
            backup_path = SaveFileService.backup_project(
                project=project,
                game_id=installed_game.game_id,
            )

        restore_directory = RestoreService._get_restore_directory(
            project_version
        )

        SaveFileService.synchronize_project(
            project=project,
            source_directory=restore_directory,
        )

        return ProjectVersionService.create_version(
            project_id=project.id,
            created_by=restored_by,
            source_type=ProjectVersionSource.RESTORED,
            backup_path=(
                str(backup_path)
                if backup_path is not None
                else None
            ),
            parent_version_id=(
                latest_version.id
                if latest_version is not None
                else None
            ),
            restored_from_version_id=project_version.id,
            lineage_name=(
                latest_version.lineage_name
                if latest_version is not None
                else project_version.lineage_name
            ),
            notes=None,
        )

    @staticmethod
    def _get_project(
        project_version: ProjectVersion,
    ) -> Project:
        project = ProjectRepository.get_by_id(
            project_version.project_id
        )

        if project is None:
            raise ValueError(
                f"Project not found for version: "
                f"{project_version.id}"
            )

        return project

    @staticmethod
    def _get_restore_directory(
        project_version: ProjectVersion,
    ) -> Path:
        # A RESTORED entry represents the contents of the version it
        # restored from. Its own backup_path contains the state that was
        # replaced, so it must not be used as its restore source.
        if project_version.restored_from_version_id is not None:
            restored_from_version = (
                ProjectVersionRepository.get_by_id(
                    project_version.restored_from_version_id
                )
            )

            if restored_from_version is None:
                raise ValueError(
                    "The version this restore was based on could not be found."
                )

            return RestoreService._get_restore_directory(
                restored_from_version
            )

        package_path = (
            Path(project_version.package_path)
            if project_version.package_path
            else None
        )

        if package_path is not None and package_path.exists():
            return RestoreService._restore_directory_from_package(
                package_path
            )

        backup_path = (
            Path(project_version.backup_path)
            if project_version.backup_path
            else None
        )

        if backup_path is not None and backup_path.exists():
            return RestoreService._restore_directory_from_backup(
                backup_path
            )

        raise FileNotFoundError(
            "No restore source found. "
            "The package and backup for this version are missing."
        )

    @staticmethod
    def _restore_directory_from_package(
        package_path: Path,
    ) -> Path:
        PackageReader.read(package_path)
        return PackageExtractor.extract(package_path)

    @staticmethod
    def _restore_directory_from_backup(
        backup_path: Path,
    ) -> Path:
        return backup_path
