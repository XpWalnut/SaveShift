from app.games.base import GameDiscovery, SupportedGame
from app.games.game_id import GameId
from app.games.valheim.discovery import ValheimDiscovery


class ValheimGame(SupportedGame):
    game_id = GameId.VALHEIM
    display_name = "Valheim"
    process_names = ["valheim.exe"]

    def discovery(self) -> GameDiscovery:
        return ValheimDiscovery()