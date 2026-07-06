from pathlib import Path

from app.database.database import SessionLocal
from app.database.models.installed_game import InstalledGame
from app.database.models.project import Project
from app.games.registry import GameRegistry
from app.utils.logging import logger


class ProjectService:
    @staticmethod
    def get_projects() -> list[Project]:
        with SessionLocal() as session:
            return session.query(Project).order_by(Project.name).all()

    @staticmethod
    def get_projects_for_installed_game(installed_game_id: int) -> list[Project]:
        with SessionLocal() as session:
            return (
                session.query(Project)
                .filter(Project.installed_game_id == installed_game_id)
                .order_by(Project.name)
                .all()
            )

    @staticmethod
    def discover_projects(installed_game_id: int) -> list[Project]:
        with SessionLocal() as session:
            installed_game = (
                session.query(InstalledGame)
                .filter(InstalledGame.id == installed_game_id)
                .first()
            )

            if installed_game is None:
                logger.warning("Project discovery failed. Installed game ID %s was not found.", installed_game_id)
                return []

            supported_game = GameRegistry.get_by_game_id(installed_game.game_id)

            if supported_game is None:
                logger.warning("Project discovery failed. Unsupported game ID: %s", installed_game.game_id)
                return []

            logger.info("Discovering projects for %s", installed_game.display_name)

            discovered_projects = supported_game.discovery().discover_projects(
                Path(installed_game.save_path)
            )

            tracked_projects: list[Project] = []

            for discovered_project in discovered_projects:
                existing_project = (
                    session.query(Project)
                    .filter(Project.installed_game_id == installed_game.id)
                    .filter(Project.name == discovered_project.name)
                    .first()
                )

                if existing_project:
                    tracked_projects.append(existing_project)
                    continue

                project = Project(
                    installed_game_id=installed_game.id,
                    name=discovered_project.name,
                    local_path=str(discovered_project.root_path),
                )

                session.add(project)
                tracked_projects.append(project)

            session.commit()

            for project in tracked_projects:
                session.refresh(project)

            logger.info(
                "Project discovery complete for %s. Found %d project(s).",
                installed_game.display_name,
                len(tracked_projects),
            )

            return tracked_projects