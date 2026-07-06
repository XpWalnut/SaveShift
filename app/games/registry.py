from app.games.abiotic_factor.definition import AbioticFactorGame
from app.games.base import SupportedGame
from app.games.game_id import GameId
from app.games.valheim.definition import ValheimGame


class GameRegistry:
    _games: dict[GameId, SupportedGame] = {
        ValheimGame.game_id: ValheimGame(),
        AbioticFactorGame.game_id: AbioticFactorGame(),
    }

    @classmethod
    def all(cls) -> list[SupportedGame]:
        return list(cls._games.values())

    @classmethod
    def get_by_game_id(cls, game_id: str | GameId) -> SupportedGame | None:
        try:
            normalized_game_id = GameId(game_id)
        except ValueError:
            return None

        return cls._games.get(normalized_game_id)

    @classmethod
    def get_by_display_name(cls, display_name: str) -> SupportedGame | None:
        normalized = display_name.strip().lower()

        for game in cls._games.values():
            if game.display_name.lower() == normalized:
                return game

        return None