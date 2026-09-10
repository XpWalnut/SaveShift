from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.games.game_id import GameId
from app.games.launcher import GameLauncher
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
        game_metadata: dict[str, Any] | None = None,
    ) -> ImportTarget:
        """Returns the folder that should receive imported save files."""
        pass


class SupportedGame(ABC):
    game_id: GameId
    display_name: str
    process_names: list[str]
    steam_app_id: int

    @abstractmethod
    def discovery(self) -> GameDiscovery:
        pass

    @abstractmethod
    def detect_save_path(self) -> Path | None:
        """Return the default save folder if it exists."""
        pass

    def is_running(self) -> bool:
        return GameLauncher.is_any_process_running(
            self.process_names
        )

    def launch(self) -> None:
        if self.is_running():
            return

        GameLauncher.launch_steam_game(self.steam_app_id)

    def join_hosted_session(self) -> None:
        """Open the game for a remotely hosted Save Shift project.

        Games that expose a supported direct-connect mechanism can override
        this method without changing the project-card workflow.
        """
        self.launch()
