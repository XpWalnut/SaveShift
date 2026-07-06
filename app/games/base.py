from dataclasses import dataclass
from pathlib import Path
from abc import ABC, abstractmethod


@dataclass(frozen=True)
class GameWorld:
    name: str
    path: Path
    files: list[Path]


class SupportedGame(ABC):
    game_id: str
    display_name: str
    process_names: list[str]

    @abstractmethod
    def scan_worlds(self, save_path: Path) -> list[GameWorld]:
        pass