from abc import ABC, abstractmethod
from pathlib import Path

from app.games.game_id import GameId
from app.games.project_discovery import DiscoveredProject


class GameDiscovery(ABC):
    @abstractmethod
    def discover_projects(self, save_path: Path) -> list[DiscoveredProject]:
        pass


class SupportedGame(ABC):
    game_id: GameId
    display_name: str
    process_names: list[str]

    @abstractmethod
    def discovery(self) -> GameDiscovery:
        pass