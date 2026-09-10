from pathlib import Path

from app.games.base import GameDiscovery
from app.games.project_discovery import DiscoveredProject, ImportTarget


class ValheimDiscovery(GameDiscovery):
    def discover_projects(self, save_path: Path) -> list[DiscoveredProject]:
        discovered_projects: list[DiscoveredProject] = []

        if not save_path.exists():
            return discovered_projects

        projects_by_name: dict[str, DiscoveredProject] = {}

        for db_file in save_path.glob("*.db"):
            project_name = db_file.stem
            fwl_file = save_path / f"{project_name}.fwl"

            save_files = [db_file]

            if fwl_file.exists():
                save_files.append(fwl_file)

            projects_by_name[project_name] = DiscoveredProject(
                name=project_name,
                root_path=save_path,
                save_files=save_files,
                metadata={
                    "file_count": len(save_files),
                    "storage_layout": "flat",
                },
            )

        for world_directory in save_path.iterdir():
            if (
                not world_directory.is_dir()
                or "_backup_" in world_directory.name.casefold()
            ):
                continue

            has_database = any(world_directory.glob("_main.*.db2"))
            has_metadata = any(world_directory.glob("_main.*.fwl2"))

            if not has_database or not has_metadata:
                continue

            save_files = sorted(
                path
                for path in world_directory.rglob("*")
                if path.is_file()
            )

            if not save_files:
                continue

            projects_by_name[world_directory.name] = DiscoveredProject(
                name=world_directory.name,
                root_path=world_directory,
                save_files=save_files,
                metadata={
                    "file_count": len(save_files),
                    "storage_layout": "chunked_directory",
                    "world_directory": world_directory.name,
                },
            )

        discovered_projects.extend(projects_by_name.values())
        return sorted(discovered_projects, key=lambda project: project.name.lower())

    def get_import_target(
            self,
            save_path: Path,
            project_name: str,
    ) -> ImportTarget:
        if (game_metadata or {}).get("storage_layout") == "chunked_directory":
            world_directory = (game_metadata or {}).get("world_directory")

            if (
                not isinstance(world_directory, str)
                or not world_directory.strip()
                or Path(world_directory).name != world_directory
                or world_directory in {".", ".."}
            ):
                raise ValueError(
                    "The Valheim package contains an invalid world directory."
                )

            return ImportTarget(project_root=save_path / world_directory)

        return ImportTarget(
            project_root=save_path
        )