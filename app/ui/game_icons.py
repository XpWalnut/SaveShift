"""Local Steam game-icon lookup for the installed-games sidebar."""

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from app.games.registry import GameRegistry
from app.steam.library import SteamLibraryService


@lru_cache(maxsize=64)
def steam_game_icon_path(game_id: str) -> Path | None:
    """Return Steam's cached app icon without downloading or persisting assets."""
    game = GameRegistry.get_by_game_id(game_id)
    steam_root = SteamLibraryService.detect_steam_root()
    if game is None or steam_root is None:
        return None
    cache = steam_root / "appcache" / "librarycache"
    app_id = game.steam_app_id
    for suffix in (".jpg", ".png", ".ico"):
        candidate = cache / f"{app_id}_icon{suffix}"
        if candidate.is_file():
            return candidate
    return None


def steam_game_pixmap(game_id: str, size: int = 24) -> QPixmap | None:
    path = steam_game_icon_path(game_id)
    if path is None:
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
