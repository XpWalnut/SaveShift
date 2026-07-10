from pathlib import Path

from app.games.base import GameDiscovery, SupportedGame
from app.games.game_id import GameId
from app.games.valheim.discovery import ValheimDiscovery


class ValheimGame(SupportedGame):
    game_id = GameId.VALHEIM
    display_name = "Valheim"
    process_names = ["valheim.exe"]

    def discovery(self) -> GameDiscovery:
        return ValheimDiscovery()

    def detect_save_path(self) -> Path | None:
        path = (
                Path.home()
                / "AppData"
                / "LocalLow"
                / "IronGate"
                / "Valheim"
                / "worlds_local"
        )

        return path if path.exists() else None