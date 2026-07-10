from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.games.game_id import GameId
from app.games.project_discovery import DiscoveredProject, ImportTarget


class GameDiscovery(ABC):
    @abstractmethod
    def discover_projects(self, save_path: Path) -> list[DiscoveredProject]:
        pass


    @abstractmethod
    def get_import_target(
        self,
        save_path: Path,
        project_name: str,
    ) -> ImportTarget:
        """Returns the folder that should receive imported save files."""
        pass


class SupportedGame(ABC):
    game_id: GameId
    display_name: str
    process_names: list[str]

    @abstractmethod
    def discovery(self) -> GameDiscovery:
        pass

    @abstractmethod
    def detect_save_path(self) -> Path | None:
        """Return the default save folder if it exists."""
        pass