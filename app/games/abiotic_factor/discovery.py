from pathlib import Path

from app.games.base import GameDiscovery
from app.games.project_discovery import DiscoveredProject, ImportTarget


class AbioticFactorDiscovery(GameDiscovery):
    def discover_projects(self, save_path: Path) -> list[DiscoveredProject]:
        discovered_projects: list[DiscoveredProject] = []

        if not save_path.exists():
            return discovered_projects

        for steam_user_folder in save_path.iterdir():
            if not steam_user_folder.is_dir():
                continue

            worlds_folder = steam_user_folder / "Worlds"

            if not worlds_folder.exists() or not worlds_folder.is_dir():
                continue

            for world_folder in worlds_folder.iterdir():
                if not world_folder.is_dir():
                    continue

                save_files = [
                    path
                    for path in world_folder.rglob("*")
                    if path.is_file()
                ]

                if not save_files:
                    continue

                discovered_projects.append(
                    DiscoveredProject(
                        name=world_folder.name,
                        root_path=world_folder,
                        save_files=save_files,
                        metadata={
                            "steam_user_id": steam_user_folder.name,
                            "file_count": len(save_files),
                        },
                    )
                )

        return sorted(discovered_projects, key=lambda project: project.name.lower())

    def get_import_target(
            self,
            save_path: Path,
            project_name: str,
    ) -> ImportTarget:
        steam_users = [
            path
            for path in save_path.iterdir()
            if path.is_dir()
        ]

        if len(steam_users) != 1:
            raise RuntimeError(
                "Unable to determine which Steam profile should receive the imported project."
            )

        return ImportTarget(
            project_root=steam_users[0] / "Worlds" / project_name
        )