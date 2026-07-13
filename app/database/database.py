import os
import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import AppConfig


def _resolve_database_path() -> str:
    configured_path = os.environ.get("SAVESHIFT_DATABASE_PATH")

    if configured_path:
        return configured_path

    if "pytest" in sys.modules:
        raise RuntimeError(
            "Refusing to use the application database from pytest. "
            "Set SAVESHIFT_DATABASE_PATH to an isolated test database "
            "before importing app.database.database."
        )

    return str(AppConfig.get_database_path())


database_path = _resolve_database_path()

engine = create_engine(f"sqlite:///{database_path}", echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app.database.models.installed_game import InstalledGame
    from app.database.models.project import Project
    from app.database.models.project_version import ProjectVersion

    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations() -> None:
    inspector = inspect(engine)

    if "project_versions" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("project_versions")
    }

    if "restored_from_version_id" not in existing_columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    ALTER TABLE project_versions
                    ADD COLUMN restored_from_version_id INTEGER
                    REFERENCES project_versions(id)
                    """
                )
            )
