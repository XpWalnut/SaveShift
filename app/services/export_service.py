from pathlib import Path
from shutil import copy2

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.services.hosting_service import HostingService


class ExportService:
    @staticmethod
    def export_project(
        project: Project,
        game_id: str,
        exported_by: str,
        destination_path: Path,
        journal_title: str | None = None,
        journal_body: str | None = None,
        source_device_name: str | None = None,
    ) -> ProjectVersion:
        version = HostingService.host_project(
            project_id=project.id,
            game_id=game_id,
            hosted_by=exported_by,
            notes="Exported manually from Save Shift",
            journal_title=journal_title,
            journal_body=journal_body,
            source_device_name=source_device_name,
        )

        if not version.package_path:
            raise RuntimeError(
                "Save Shift created the version but no package path was recorded."
            )

        source_path = Path(version.package_path)

        if not source_path.exists():
            raise FileNotFoundError(
                f"The generated package could not be found:\n{source_path}"
            )

        destination_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        copy2(source_path, destination_path)

        return version
