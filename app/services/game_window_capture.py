import csv
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess

from PySide6.QtGui import QGuiApplication

from app.core.logging import logger


class GameWindowCapture:
    """Best-effort capture of a visible supported-game window on Windows."""

    @classmethod
    def capture(cls, process_names: list[str], destination: Path) -> Path | None:
        window_id = cls._game_window_id(process_names)
        if window_id is None:
            return None
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        pixmap = screen.grabWindow(window_id)
        if pixmap.isNull() or pixmap.width() < 320 or pixmap.height() < 200:
            return None
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not pixmap.save(str(destination), "JPG", 84):
            return None
        return destination

    @staticmethod
    def _process_ids(process_names: list[str]) -> set[int]:
        names = {name.casefold() for name in process_names}
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError) as error:
            logger.debug("Could not enumerate game processes for capture: %s", error)
            return set()
        return {
            int(row[1])
            for row in csv.reader(result.stdout.splitlines())
            if len(row) >= 2 and row[0].casefold() in names and row[1].isdigit()
        }

    @classmethod
    def _game_window_id(cls, process_names: list[str]) -> int | None:
        process_ids = cls._process_ids(process_names)
        if not process_ids or not hasattr(ctypes, "WINFUNCTYPE"):
            return None
        user32 = ctypes.windll.user32
        candidates: list[tuple[int, int]] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if process_id.value not in process_ids:
                return True
            rectangle = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rectangle)):
                width = max(0, rectangle.right - rectangle.left)
                height = max(0, rectangle.bottom - rectangle.top)
                if width >= 320 and height >= 200:
                    candidates.append((width * height, int(hwnd)))
            return True

        user32.EnumWindows(visit, 0)
        return max(candidates, default=(0, 0))[1] or None
