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

            discovered_names = {project.name for project in discovered_projects}

            existing_projects = (
                session.query(Project)
                .filter(Project.installed_game_id == installed_game.id)
                .all()
            )

            existing_by_name = {
                project.name: project
                for project in existing_projects
            }

            tracked_projects: list[Project] = []

            for discovered_project in discovered_projects:
                existing_project = existing_by_name.get(discovered_project.name)

                if existing_project:
                    existing_project.local_path = str(discovered_project.root_path)
                    tracked_projects.append(existing_project)
                    continue

                project = Project(
                    installed_game_id=installed_game.id,
                    name=discovered_project.name,
                    local_path=str(discovered_project.root_path),
                )

                session.add(project)
                tracked_projects.append(project)

            for existing_project in existing_projects:
                if existing_project.name not in discovered_names:
                    logger.info(
                        "Removing stale project from database: %s",
                        existing_project.name,
                    )
                    session.delete(existing_project)

            session.commit()

            for project in tracked_projects:
                session.refresh(project)

            logger.info(
                "Project discovery complete for %s. Tracking %d project(s).",
                installed_game.display_name,
                len(tracked_projects),
            )

            return tracked_projects