from datetime import UTC, datetime

from app.database.models.project_version import ProjectVersion
from app.database.repositories.project_version_repository import ProjectVersionRepository


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
        package_path: str | None = None,
        backup_path: str | None = None,
        package_checksum: str | None = None,
        parent_version_id: int | None = None,
        lineage_name: str = "main",
        notes: str | None = None,
    ) -> ProjectVersion:
        latest_version = ProjectVersionRepository.get_latest(project_id)

        next_version_number = (
            latest_version.version_number + 1
            if latest_version is not None
            else 1
        )

        project_version = ProjectVersion(
            project_id=project_id,
            version_number=next_version_number,
            created_at_utc=datetime.now(UTC),
            created_by=created_by.strip(),
            source_type=source_type,
            package_path=package_path,
            backup_path=backup_path,
            package_checksum=package_checksum,
            parent_version_id=parent_version_id,
            lineage_name=lineage_name,
            notes=notes,
        )

        return ProjectVersionRepository.add(project_version)

    @staticmethod
    def get_versions_for_project(project_id: int) -> list[ProjectVersion]:
        return ProjectVersionRepository.get_by_project(project_id)

    @staticmethod
    def get_latest_version(project_id: int) -> ProjectVersion | None:
        return ProjectVersionRepository.get_latest(project_id)