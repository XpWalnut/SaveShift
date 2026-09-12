from pathlib import Path

from app.database.database import SessionLocal
from app.database.models.project import Project
from app.games.project_discovery import DiscoveredProject
from app.core.logging import logger


class ProjectRepository:
    @staticmethod
    def get_all() -> list[Project]:
        with SessionLocal() as session:
            return session.query(Project).order_by(Project.name).all()

    @staticmethod
    def get_by_id(project_id: int) -> Project | None:
        with SessionLocal() as session:
            return session.get(Project, project_id)

    @staticmethod
    def get_by_uuid(project_uuid: str) -> Project | None:
        with SessionLocal() as session:
            return (
                session.query(Project)
                .filter(Project.uuid == project_uuid)
                .first()
            )

    @staticmethod
    def get_for_installed_game(installed_game_id: int) -> list[Project]:
        with SessionLocal() as session:
            return (
                session.query(Project)
                .filter(Project.installed_game_id == installed_game_id)
                .order_by(Project.name)
                .all()
            )

    @staticmethod
    def get_for_group(group_id: str) -> list[Project]:
        with SessionLocal() as session:
            return (
                session.query(Project)
                .filter(Project.coordination_group_id == group_id)
                .order_by(Project.name)
                .all()
            )

    @staticmethod
    def associate_group(project_id: int, group_id: str | None) -> Project:
        with SessionLocal() as session:
            project = session.get(Project, project_id)
            if project is None:
                raise ValueError(f"Project not found: {project_id}")
            project.coordination_group_id = group_id
            session.commit()
            session.refresh(project)
            return project

    @staticmethod
    def associate_unassigned(group_id: str) -> int:
        with SessionLocal() as session:
            count = (
                session.query(Project)
                .filter(Project.coordination_group_id.is_(None))
                .update({Project.coordination_group_id: group_id})
            )
            session.commit()
            return int(count)

    @staticmethod
    def get_by_local_path(local_path: Path) -> Project | None:
        expected = str(local_path.resolve(strict=False)).casefold()

        for project in ProjectRepository.get_all():
            actual = str(
                Path(project.local_path).resolve(strict=False)
            ).casefold()

            if actual == expected:
                return project

        return None

    @staticmethod
    def adopt_identity(
        project_id: int,
        project_uuid: str,
        name: str,
    ) -> Project:
        with SessionLocal() as session:
            project = session.get(Project, project_id)

            if project is None:
                raise ValueError(f"Project not found: {project_id}")

            project.uuid = project_uuid
            project.name = name
            session.commit()
            session.refresh(project)
            return project

    @staticmethod
    def synchronize(
        installed_game_id: int,
        discovered_projects: list[DiscoveredProject],
    ) -> list[Project]:
        with SessionLocal() as session:
            discovered_names = {project.name for project in discovered_projects}

            existing_projects = (
                session.query(Project)
                .filter(Project.installed_game_id == installed_game_id)
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
                    installed_game_id=installed_game_id,
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

            return tracked_projects

    @staticmethod
    def create(
            installed_game_id: int,
            project_uuid: str,
            name: str,
            local_path: Path,
            coordination_group_id: str | None = None,
    ) -> Project:
        with SessionLocal() as session:
            project = Project(
                installed_game_id=installed_game_id,
                uuid=project_uuid,
                name=name,
                local_path=str(local_path),
                coordination_group_id=coordination_group_id,
            )

            session.add(project)
            session.commit()
            session.refresh(project)

            return project
