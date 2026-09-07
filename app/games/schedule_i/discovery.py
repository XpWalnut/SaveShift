import json
from pathlib import Path
from typing import Any

from app.games.base import GameDiscovery
from app.games.project_discovery import DiscoveredProject, ImportTarget


SAVE_SLOT_PREFIX = "SaveGame_"
MAX_SAVE_SLOTS = 5


class ScheduleIDiscovery(GameDiscovery):
    def discover_projects(
        self,
        save_path: Path,
    ) -> list[DiscoveredProject]:
        discovered_projects: list[DiscoveredProject] = []

        if not save_path.is_dir():
            return discovered_projects

        for steam_user_folder in save_path.iterdir():
            if not steam_user_folder.is_dir():
                continue

            for save_folder in steam_user_folder.iterdir():
                slot_number = _slot_number(save_folder)

                if slot_number is None:
                    continue

                save_files = sorted(
                    path
                    for path in save_folder.rglob("*")
                    if path.is_file()
                )

                if not save_files:
                    continue

                project_name = _read_organization_name(save_folder)
                metadata = _read_json(save_folder / "Metadata.json")

                discovered_projects.append(
                    DiscoveredProject(
                        name=project_name or f"Save Game {slot_number}",
                        root_path=save_folder,
                        save_files=save_files,
                        metadata={
                            "steam_user_id": steam_user_folder.name,
                            "save_slot": slot_number,
                            "game_version": metadata.get("GameVersion"),
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
        game_metadata: dict[str, Any] | None = None,
    ) -> ImportTarget:
        steam_users = [
            path
            for path in save_path.iterdir()
            if path.is_dir()
        ] if save_path.is_dir() else []

        if len(steam_users) != 1:
            raise RuntimeError(
                "Unable to determine which Steam profile should receive "
                "the imported Schedule I project."
            )

        steam_user = steam_users[0]

        matching_saves = [
            save_folder
            for save_folder in steam_user.iterdir()
            if save_folder.is_dir()
            and _slot_number(save_folder) is not None
            and _read_organization_name(save_folder) == project_name
        ]

        if len(matching_saves) == 1:
            return ImportTarget(project_root=matching_saves[0])

        if len(matching_saves) > 1:
            raise RuntimeError(
                "Multiple Schedule I saves use this organization name. "
                "Rename one of them in game before importing."
            )

        occupied_slots = {
            slot_number
            for save_folder in steam_user.iterdir()
            if (slot_number := _slot_number(save_folder)) is not None
        }

        for slot_number in range(1, MAX_SAVE_SLOTS + 1):
            if slot_number not in occupied_slots:
                return ImportTarget(
                    project_root=(
                        steam_user / f"{SAVE_SLOT_PREFIX}{slot_number}"
                    )
                )

        raise RuntimeError(
            "All Schedule I save slots are occupied. Free a slot in game "
            "before importing this project."
        )


def _slot_number(save_folder: Path) -> int | None:
    if not save_folder.is_dir() or not save_folder.name.startswith(
        SAVE_SLOT_PREFIX
    ):
        return None

    suffix = save_folder.name.removeprefix(SAVE_SLOT_PREFIX)

    if not suffix.isdigit():
        return None

    slot_number = int(suffix)
    return slot_number if slot_number > 0 else None


def _read_organization_name(save_folder: Path) -> str | None:
    game_data = _read_json(save_folder / "Game.json")
    organization_name = game_data.get("OrganisationName")

    if isinstance(organization_name, str) and organization_name.strip():
        return organization_name.strip()

    return None


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as json_file:
            value = json.load(json_file)
    except (OSError, json.JSONDecodeError):
        return {}

    return value if isinstance(value, dict) else {}
