from pathlib import Path

from app.database.database import SessionLocal
from app.database.models.project import Project
from app.database.models.installed_game import InstalledGame
from app.games.registry import GameRegistry


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
                return []

            supported_game = GameRegistry.get_by_game_id(installed_game.game_id)

            if supported_game is None:
                return []

            discovered_worlds = supported_game.scan_worlds(Path(installed_game.save_path))
            saved_projects: list[Project] = []

            for world in discovered_worlds:
                existing_project = (
                    session.query(Project)
                    .filter(Project.installed_game_id == installed_game.id)
                    .filter(Project.name == world.name)
                    .first()
                )

                if existing_project:
                    saved_projects.append(existing_project)
                    continue

                project = Project(
                    installed_game_id=installed_game.id,
                    name=world.name,
                    local_path=str(world.path),
                )
                session.add(project)
                saved_projects.append(project)

            session.commit()

            for project in saved_projects:
                session.refresh(project)

            return saved_projects