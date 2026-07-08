from pathlib import Path

from app.database.repositories.project_repository import ProjectRepository
from app.packages.checksum import calculate_sha256
from app.packages.package_service import PackageService
from app.services.save_file_service import SaveFileService
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)


class HostingService:
    @staticmethod
    def host_project(
        project_id: int,
        game_id: str,
        hosted_by: str,
        notes: str | None = None,
    ):
        project = ProjectRepository.get_by_id(project_id)

        if project is None:
            raise ValueError(f"Project not found: {project_id}")

        save_files = SaveFileService.list_project_files(project)

        project_version_number = ProjectVersionService.get_next_version_number(project.id)

        package_path = PackageService.create_project_package(
            game_id=game_id,
            project=project,
            project_version=project_version_number,
            save_files=save_files,
            created_by=hosted_by,
        )

        package_checksum = calculate_sha256(package_path)

        return ProjectVersionService.create_version(
            project_id=project.id,
            created_by=hosted_by,
            source_type=ProjectVersionSource.HOSTED,
            version_number=project_version_number,
            package_path=str(package_path),
            package_checksum=package_checksum,
            notes=notes,
        )