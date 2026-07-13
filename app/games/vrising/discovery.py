import json
from pathlib import Path

from app.games.base import GameDiscovery
from app.games.project_discovery import DiscoveredProject, ImportTarget


class VRisingDiscovery(GameDiscovery):
    def discover_projects(
        self,
        save_path: Path,
    ) -> list[DiscoveredProject]:
        discovered_projects: list[DiscoveredProject] = []

        if not save_path.exists():
            return discovered_projects

        for steam_user_folder in save_path.iterdir():
            if not steam_user_folder.is_dir():
                continue

            version_folder = steam_user_folder / "v4"

            if not version_folder.is_dir():
                continue

            for world_folder in version_folder.iterdir():
                if not world_folder.is_dir():
                    continue

                project_name = self._get_project_name(world_folder)

                save_files = [
                    path
                    for path in world_folder.rglob("*")
                    if path.is_file()
                    and ".BACKUP" not in path.parts
                    and ".TEMP" not in path.parts
                ]

                if not save_files:
                    continue

                discovered_projects.append(
                    DiscoveredProject(
                        name=project_name,
                        root_path=world_folder,
                        save_files=save_files,
                        metadata={
                            "steam_user_id": steam_user_folder.name,
                            "world_uuid": world_folder.name,
                            "file_count": len(save_files),
                        },
                    )
                )

        return sorted(
            discovered_projects,
            key=lambda project: project.name.lower(),
        )

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
                "Unable to determine which Steam profile should "
                "receive the imported V Rising project."
            )

        raise NotImplementedError(
            "V Rising imports need the original save UUID, "
            "not only the project display name."
        )

    @staticmethod
    def _get_project_name(world_folder: Path) -> str:
        settings_path = world_folder / "ServerHostSettings.json"

        if not settings_path.exists():
            return world_folder.name

        try:
            with settings_path.open(
                "r",
                encoding="utf-8",
            ) as settings_file:
                settings = json.load(settings_file)
        except (OSError, json.JSONDecodeError):
            return world_folder.name

        name = settings.get("Name")

        if isinstance(name, str) and name.strip():
            return name.strip()

        return world_folder.name