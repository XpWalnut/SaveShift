from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import AppConfig

engine = create_engine(f"sqlite:///{AppConfig.get_database_path()}", echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app.database.models.installed_game import InstalledGame
    from app.database.models.project import Project
    from app.database.models.project_version import ProjectVersion

    Base.metadata.create_all(bind=engine)