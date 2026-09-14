from functools import lru_cache

from PySide6.QtCore import QByteArray, QSize
from PySide6.QtGui import QIcon, QPixmap

from app.ui import theme


_PATHS = {
    "play": '<path d="M8 5l11 7-11 7z" fill="currentColor" stroke="none"/>',
    "upload": '<path d="M12 17V4m0 0L7 9m5-5 5 5M5 15v5h14v-5"/>',
    "download": '<path d="M12 4v13m0 0-5-5m5 5 5-5M5 20h14"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    "journal": '<path d="M6 3h9l4 4v14H6zM15 3v5h4M9 12h7M9 16h7"/>',
    "share": '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.2 10.9l7.5-3.8M8.2 13.1l7.5 3.8"/>',
    "unshare": '<path d="M9 15l-2 2a3 3 0 01-4-4l4-4a3 3 0 014 0M15 9l2-2a3 3 0 014 4l-4 4a3 3 0 01-4 0M8 12h8M4 4l16 16"/>',
    "group": '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20v-2a6 6 0 0112 0v2M15 14a5 5 0 016 5v1"/>',
    "invite": '<circle cx="8" cy="8" r="3"/><path d="M2 20v-2a6 6 0 0112 0v2M18 8v8M14 12h8"/>',
    "add": '<path d="M12 4v16M4 12h16"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="M14.5 14.5L21 21"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19 13.5l2 1.5-2 3.5-2.5-1a8 8 0 01-2.5 1.5L13.5 22h-4L9 19a8 8 0 01-2.5-1.5l-2.5 1L2 15l2-1.5a8 8 0 010-3L2 9l2-3.5 2.5 1A8 8 0 019 5L9.5 2h4L14 5a8 8 0 012.5 1.5l2.5-1L21 9l-2 1.5a8 8 0 010 3z"/>',
    "help": '<circle cx="12" cy="12" r="10"/><path d="M9.5 9a2.7 2.7 0 115 1.4c-1.5 1.2-2.5 1.6-2.5 3.6M12 18h.01"/>',
    "game": '<path d="M7 9h10a5 5 0 014.5 7l-1 2a2 2 0 01-3 .5L15 16H9l-2.5 2.5a2 2 0 01-3-.5l-1-2A5 5 0 017 9zM7 12v4M5 14h4M17 13h.01M19 15h.01"/>',
    "inbox": '<path d="M4 5h16v14H4zM4 14h5l2 2h2l2-2h5"/>',
    "camera": '<path d="M4 7h4l2-2h4l2 2h4v13H4z"/><circle cx="12" cy="13" r="4"/>',
}


@lru_cache(maxsize=128)
def icon(name: str, color: str = theme.TEXT_SECONDARY, size: int = 20) -> QIcon:
    path = _PATHS[name]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24">
    <g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="color:{color}">{path}</g></svg>'''
    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(svg.encode("utf-8")), "SVG")
    return QIcon(pixmap)


def apply_icon(button, name: str, *, primary: bool = False) -> None:
    button.setIcon(icon(name, theme.TEXT_PRIMARY if primary else theme.TEXT_SECONDARY))
    button.setIconSize(QSize(19, 19))
