from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

APP_DATA_DIR = Path.home() / ".saveshift"
APP_DATA_DIR.mkdir(exist_ok=True)

DATABASE_PATH = APP_DATA_DIR / "saveshift.sqlite3"

engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app.models.installed_game import InstalledGame
    from app.models.project import Project

    Base.metadata.create_all(bind=engine)