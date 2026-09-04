from pathlib import Path

from app.database.models.installed_game import InstalledGame
from app.database.repositories.installed_game_repository import InstalledGameRepository
from app.core.logging import logger
from app.games.registry import GameRegistry
from app.steam.library import SteamLibraryService


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

    @staticmethod
    def detect_steam_games(
        steam_root: Path | None = None,
    ) -> list[InstalledGame]:
        installations = SteamLibraryService.find_installed_apps(steam_root)
        configured_game_ids = {
            installed_game.game_id
            for installed_game in InstalledGameRepository.get_all()
        }
        added_games: list[InstalledGame] = []

        for supported_game in GameRegistry.all():
            if supported_game.game_id.value in configured_game_ids:
                continue

            if supported_game.steam_app_id not in installations:
                continue

            save_path = supported_game.detect_save_path()

            if save_path is None:
                continue

            added_games.append(
                InstalledGameService.add_installed_game(
                    game_id=supported_game.game_id.value,
                    display_name=supported_game.display_name,
                    save_path=str(save_path),
                )
            )

        return added_games
