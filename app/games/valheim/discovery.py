from pathlib import Path
from typing import Any

from app.games.base import GameDiscovery
from app.games.project_discovery import DiscoveredProject, ImportTarget


class ValheimDiscovery(GameDiscovery):
    def discover_projects(self, save_path: Path) -> list[DiscoveredProject]:
        discovered_projects: list[DiscoveredProject] = []

        if not save_path.exists():
            return discovered_projects

        for db_file in save_path.glob("*.db"):
            project_name = db_file.stem
            fwl_file = save_path / f"{project_name}.fwl"

            save_files = [db_file]

            if fwl_file.exists():
                save_files.append(fwl_file)

            discovered_projects.append(
                DiscoveredProject(
                    name=project_name,
                    root_path=save_path,
                    save_files=save_files,
                    metadata={
                        "file_count": len(save_files),
                    },
                )
            )

        return sorted(discovered_projects, key=lambda project: project.name.lower())

    def get_import_target(
            self,
        save_path: Path,
        project_name: str,
        game_metadata: dict[str, Any] | None = None,
    ) -> ImportTarget:
        return ImportTarget(
            project_root=save_path
        )
