from datetime import UTC, datetime
from pathlib import Path
import re
import shutil

from app.core.config import AppConfig
from app.database.models.project import Project
from app.games.game_id import GameId


class SaveFileService:
    @staticmethod
    def list_project_files(
        project: Project,
        game_id: str | None = None,
    ) -> list[Path]:
        project_root = Path(project.local_path)

        if not project_root.exists():
            raise FileNotFoundError(f"Project folder does not exist: {project_root}")

        if not project_root.is_dir():
            raise NotADirectoryError(f"Project path is not a folder: {project_root}")

        files = [
            path
            for path in project_root.rglob("*")
            if path.is_file()
        ]
        managed_paths = SaveFileService._managed_relative_paths(
            project,
            game_id,
        )
        if managed_paths is None:
            return files
        return [
            path
            for path in files
            if path.relative_to(project_root) in managed_paths
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

        managed_paths = SaveFileService._managed_relative_paths(
            project,
            game_id,
        )
        if managed_paths is None:
            shutil.copytree(project_root, backup_root)
        else:
            backup_root.mkdir(parents=True)
            for relative_path in managed_paths:
                source = project_root / relative_path
                if source.is_file():
                    shutil.copy2(source, backup_root / relative_path)

        return backup_root

    @staticmethod
    def synchronize_project(
        project: Project,
        source_directory: Path,
        game_id: str | None = None,
    ) -> None:
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
        managed_paths = SaveFileService._managed_relative_paths(
            project,
            game_id,
        )

        if managed_paths is not None:
            unexpected_files = source_files - managed_paths
            if unexpected_files:
                raise ValueError(
                    "This legacy Valheim package contains files from other "
                    "worlds. Re-host the selected world with the current "
                    "version of Save Shift."
                )
            project_files &= managed_paths

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

    @staticmethod
    def _managed_relative_paths(
        project: Project,
        game_id: str | None,
    ) -> set[Path] | None:
        """Return the files owned inside a shared game save directory.

        New Valheim worlds and all other supported games have a dedicated
        project directory. Legacy Valheim worlds instead share `worlds_local`,
        so only the selected world's file pair belongs to the project.
        """
        if game_id != GameId.VALHEIM.value:
            return None

        if Path(project.name).name != project.name or project.name in {".", ".."}:
            raise ValueError("The Valheim project name is not a safe file name.")

        project_root = Path(project.local_path)
        uses_shared_flat_root = (
            project_root.name.casefold() != project.name.casefold()
        )

        if not uses_shared_flat_root:
            return None

        return {
            Path(f"{project.name}.db"),
            Path(f"{project.name}.fwl"),
        }
