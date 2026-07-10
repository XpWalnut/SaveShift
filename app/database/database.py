from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import os

from app.core.config import AppConfig

database_path = os.environ.get(
    "SAVESHIFT_DATABASE_PATH",
    str(AppConfig.get_database_path()),
)

engine = create_engine(f"sqlite:///{database_path}", echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app.database.models.installed_game import InstalledGame
    from app.database.models.project import Project
    from app.database.models.project_version import ProjectVersion

    Base.metadata.create_all(bind=engine)