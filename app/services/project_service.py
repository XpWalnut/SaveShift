from pathlib import Path

from app.database.models.project import Project
from app.database.repositories.installed_game_repository import InstalledGameRepository
from app.database.repositories.project_repository import ProjectRepository
from app.games.registry import GameRegistry
from app.core.logging import logger


class ProjectService:
    @staticmethod
    def get_projects() -> list[Project]:
        return ProjectRepository.get_all()

    @staticmethod
    def get_projects_for_installed_game(installed_game_id: int) -> list[Project]:
        return ProjectRepository.get_for_installed_game(installed_game_id)

    @staticmethod
    def create_project(
            installed_game_id: int,
            project_uuid: str,
            name: str,
            local_path: Path,
    ) -> Project:
        return ProjectRepository.create(
            installed_game_id=installed_game_id,
            project_uuid=project_uuid,
            name=name,
            local_path=local_path,
        )

    @staticmethod
    def discover_projects(installed_game_id: int) -> list[Project]:
        installed_game = InstalledGameRepository.get_by_id(installed_game_id)

        if installed_game is None:
            logger.warning("Installed game ID %s was not found.", installed_game_id)
            return []

        supported_game = GameRegistry.get_by_game_id(installed_game.game_id)

        if supported_game is None:
            logger.warning("Unsupported game ID: %s", installed_game.game_id)
            return []

        logger.info("Discovering projects for %s", installed_game.display_name)

        discovered_projects = supported_game.discovery().discover_projects(
            Path(installed_game.save_path)
        )

        tracked_projects = ProjectRepository.synchronize(
            installed_game_id=installed_game.id,
            discovered_projects=discovered_projects,
        )

        logger.info(
            "Project discovery complete for %s. Tracking %d project(s).",
            installed_game.display_name,
            len(tracked_projects),
        )

        return tracked_projects