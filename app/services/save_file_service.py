from datetime import UTC, datetime
from pathlib import Path
import re
import shutil

from app.core.config import AppConfig
from app.database.models.project import Project


class SaveFileService:
    @staticmethod
    def list_project_files(project: Project) -> list[Path]:
        project_root = Path(project.local_path)

        if not project_root.exists():
            raise FileNotFoundError(f"Project folder does not exist: {project_root}")

        if not project_root.is_dir():
            raise NotADirectoryError(f"Project path is not a folder: {project_root}")

        return [
            path
            for path in project_root.rglob("*")
            if path.is_file()
        ]

    @staticmethod
    def backup_project(project: Project, game_id: str) -> Path:
        project_root = Path(project.local_path)

        if not project_root.exists():
            raise FileNotFoundError(f"Project folder does not exist: {project_root}")

        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")

        backup_root = (
            AppConfig.get_backups_directory()
            / SaveFileService._sanitize_path_component(game_id)
            / SaveFileService._sanitize_path_component(project.name)
            / timestamp
        )

        shutil.copytree(project_root, backup_root)

        return backup_root

    @staticmethod
    def synchronize_project(project: Project, source_directory: Path) -> None:
        project_root = Path(project.local_path)
        project_root.mkdir(parents=True, exist_ok=True)

        if not project_root.is_dir():
            raise NotADirectoryError(f"Project path is not a folder: {project_root}")

        if not source_directory.exists():
            raise FileNotFoundError(f"Source folder does not exist: {source_directory}")

        if not source_directory.is_dir():
            raise NotADirectoryError(f"Source path is not a folder: {source_directory}")

        project_files = SaveFileService._relative_file_set(project_root)
        source_files = SaveFileService._relative_file_set(source_directory)

        files_to_delete = project_files - source_files

        for relative_path in files_to_delete:
            (project_root / relative_path).unlink()


        for source_file in SaveFileService._list_absolute_files(source_directory):
            relative_path = source_file.relative_to(source_directory)
            target_file = project_root / relative_path

            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)

    @staticmethod
    def _list_absolute_files(root: Path) -> list[Path]:
        return [
            path
            for path in root.rglob("*")
            if path.is_file()
        ]

    @staticmethod
    def _relative_file_set(root: Path) -> set[Path]:
        return {
            path.relative_to(root)
            for path in root.rglob("*")
            if path.is_file()
        }

    @staticmethod
    def _sanitize_path_component(value: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_")
        return sanitized or "unknown"