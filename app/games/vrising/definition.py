from pathlib import Path

from app.games.base import GameDiscovery, SupportedGame
from app.games.game_id import GameId
from app.games.vrising.discovery import VRisingDiscovery


class VRisingGame(SupportedGame):
    game_id = GameId.V_RISING
    display_name = "V Rising"
    process_names = ["VRising.exe"]
    steam_app_id = 1604030

    def discovery(self) -> GameDiscovery:
        return VRisingDiscovery()

    def detect_save_path(self) -> Path:
        return (
            Path.home()
            / "AppData"
            / "LocalLow"
            / "Stunlock Studios"
            / "VRising"
            / "CloudSaves"
        )
