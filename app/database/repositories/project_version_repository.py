from sqlalchemy import select

from app.database.database import SessionLocal
from app.database.models.project_version import ProjectVersion


class ProjectVersionRepository:

    @staticmethod
    def add(version: ProjectVersion) -> ProjectVersion:
        with SessionLocal() as session:
            session.add(version)
            session.commit()
            session.refresh(version)
            return version

    @staticmethod
    def get_by_project(project_id: int) -> list[ProjectVersion]:
        with SessionLocal() as session:
            return list(
                session.scalars(
                    select(ProjectVersion)
                    .where(ProjectVersion.project_id == project_id)
                    .order_by(ProjectVersion.version_number)
                )
            )

    @staticmethod
    def get_latest(project_id: int) -> ProjectVersion | None:
        with SessionLocal() as session:
            return session.scalar(
                select(ProjectVersion)
                .where(ProjectVersion.project_id == project_id)
                .order_by(ProjectVersion.version_number.desc())
            )