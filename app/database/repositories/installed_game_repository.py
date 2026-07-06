from app.database.database import SessionLocal
from app.database.models.installed_game import InstalledGame


class InstalledGameRepository:
    @staticmethod
    def get_all() -> list[InstalledGame]:
        with SessionLocal() as session:
            return session.query(InstalledGame).order_by(InstalledGame.display_name).all()

    @staticmethod
    def get_by_id(installed_game_id: int) -> InstalledGame | None:
        with SessionLocal() as session:
            return (
                session.query(InstalledGame)
                .filter(InstalledGame.id == installed_game_id)
                .first()
            )

    @staticmethod
    def add(game_id: str, display_name: str, save_path: str) -> InstalledGame:
        with SessionLocal() as session:
            installed_game = InstalledGame(
                game_id=game_id,
                display_name=display_name.strip(),
                save_path=save_path.strip(),
                enabled=True,
            )

            session.add(installed_game)
            session.commit()
            session.refresh(installed_game)

            return installed_game

    @staticmethod
    def delete(installed_game_id: int) -> None:
        with SessionLocal() as session:
            installed_game = (
                session.query(InstalledGame)
                .filter(InstalledGame.id == installed_game_id)
                .first()
            )

            if installed_game:
                session.delete(installed_game)
                session.commit()