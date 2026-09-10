from datetime import UTC, datetime
from pathlib import Path

from app.database.models.project_version import ProjectVersion
from app.database.repositories.project_version_repository import ProjectVersionRepository
from app.packages.package_reader import PackageReader


class ProjectVersionSource:
    HOSTED = "HOSTED"
    IMPORTED = "IMPORTED"
    RESTORED = "RESTORED"
    FORKED = "FORKED"


class ProjectVersionService:
    @staticmethod
    def create_version(
            project_id: int,
            created_by: str,
            source_type: str,
            version_number: int | None = None,
            package_path: str | None = None,
            backup_path: str | None = None,
            package_checksum: str | None = None,
            parent_version_id: int | None = None,
            restored_from_version_id: int | None = None,
            lineage_name: str = "main",
            notes: str | None = None,
    ) -> ProjectVersion:
        if version_number is None:
            version_number = ProjectVersionService.get_next_version_number(project_id)

        project_version = ProjectVersion(
            project_id=project_id,
            version_number=version_number,
            created_at_utc=datetime.now(UTC),
            created_by=created_by.strip(),
            source_type=source_type,
            package_path=package_path,
            backup_path=backup_path,
            package_checksum=package_checksum,
            parent_version_id=parent_version_id,
            restored_from_version_id=restored_from_version_id,
            lineage_name=lineage_name,
            notes=notes,
        )

        return ProjectVersionRepository.add(project_version)

    @staticmethod
    def get_versions_for_project(project_id: int) -> list[ProjectVersion]:
        return [
            ProjectVersionService._with_package_creator(version)
            for version in ProjectVersionRepository.get_by_project(project_id)
        ]

    @staticmethod
    def get_latest_version(project_id: int) -> ProjectVersion | None:
        version = ProjectVersionRepository.get_latest(project_id)

        if version is None:
            return None

        return ProjectVersionService._with_package_creator(version)

    @staticmethod
    def get_next_version_number(project_id: int) -> int:
        highest_version = ProjectVersionRepository.get_highest_version_number(
            project_id
        )

        if highest_version is None:
            return 1

        return highest_version + 1

    @staticmethod
    def _with_package_creator(version: ProjectVersion) -> ProjectVersion:
        """Correct legacy imported attribution from the package manifest."""
        if (
            version.source_type != ProjectVersionSource.IMPORTED
            or not version.package_path
        ):
            return version

        package_path = Path(version.package_path)

        if not package_path.is_file():
            return version

        try:
            package_creator = PackageReader.read(
                package_path,
                verify=False,
            ).created_by.strip()
        except Exception:
            return version

        if package_creator:
            version.created_by = package_creator

        return version
