import os
import sys

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import AppConfig
from app.database.migrations import MigrationResult, initialize_database


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


def init_db() -> MigrationResult:
    from app.database.models.installed_game import InstalledGame
    from app.database.models.project import Project
    from app.database.models.project_version import ProjectVersion
    from app.database.models.session_journal_entry import SessionJournalEntry

    return _run_migrations()


def _run_migrations() -> MigrationResult:
    return initialize_database(
        engine=engine,
        metadata=Base.metadata,
        database_path=Path(database_path),
        backup_directory=AppConfig.get_database_backups_directory(),
    )
