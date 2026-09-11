from pathlib import Path

from app.games.base import GameDiscovery, SupportedGame
from app.games.game_id import GameId
from app.games.launcher import GameLauncher
from app.games.valheim.discovery import ValheimDiscovery


class ValheimGame(SupportedGame):
    game_id = GameId.VALHEIM
    display_name = "Valheim"
    process_names = ["valheim.exe"]
    steam_app_id = 892970


    def discovery(self) -> GameDiscovery:
        return ValheimDiscovery()


    def detect_save_path(self) -> Path:
        return (
                Path.home()
                / "AppData"
                / "LocalLow"
                / "IronGate"
                / "Valheim"
                / "worlds_local"
        )
