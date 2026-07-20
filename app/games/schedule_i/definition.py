from pathlib import Path

from app.games.base import GameDiscovery, SupportedGame
from app.games.game_id import GameId
from app.games.schedule_i.discovery import ScheduleIDiscovery


class ScheduleIGame(SupportedGame):
    game_id = GameId.SCHEDULE_I
    display_name = "Schedule I"
    process_names = ["Schedule I.exe"]
    steam_app_id = 3164500

    def discovery(self) -> GameDiscovery:
        return ScheduleIDiscovery()

    def detect_save_path(self) -> Path | None:
        path = (
            Path.home()
            / "AppData"
            / "LocalLow"
            / "TVGS"
            / "Schedule I"
            / "Saves"
        )

        return path if path.exists() else None
