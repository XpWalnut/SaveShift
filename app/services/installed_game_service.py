from app.database.models.installed_game import InstalledGame
from app.database.repositories.installed_game_repository import InstalledGameRepository
from app.core.logging import logger


class InstalledGameService:
    @staticmethod
    def get_installed_games() -> list[InstalledGame]:
        return InstalledGameRepository.get_all()

    @staticmethod
    def add_installed_game(game_id: str, display_name: str, save_path: str) -> InstalledGame:
        existing_game = InstalledGameRepository.get_by_game_id(game_id)

        if existing_game is not None:
            raise ValueError(
                f"{display_name} has already been configured."
            )

        installed_game = InstalledGameRepository.add(
            game_id=game_id,
            display_name=display_name,
            save_path=save_path,
        )

        logger.info("Installed game added: %s", display_name)

        return installed_game

    @staticmethod
    def delete_installed_game(installed_game_id: int) -> None:
        InstalledGameRepository.delete(installed_game_id)