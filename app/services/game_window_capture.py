import csv
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess

from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication

from app.core.logging import logger


class GameWindowCapture:
    """Best-effort capture of a visible supported-game window on Windows."""

    @classmethod
    def capture(cls, process_names: list[str], destination: Path) -> Path | None:
        bounds = cls._game_window_bounds(process_names)
        if bounds is None:
            return None
        _window_id, left, top, width, height = bounds
        if not cls._is_foreground(_window_id):
            return None
        screen = QGuiApplication.screenAt(QPoint(left + width // 2, top + height // 2))
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        # GPU-backed game windows can return a permanently cached first frame when
        # their HWND is captured directly. Capture the live desktop pixels covering
        # the window instead. Coordinates passed for the root window are relative to
        # the selected screen, including screens positioned left/above the primary.
        geometry = screen.geometry()
        pixmap = screen.grabWindow(
            0,
            left - geometry.x(),
            top - geometry.y(),
            width,
            height,
        )
        if pixmap.isNull() or pixmap.width() < 320 or pixmap.height() < 200:
            return None
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not pixmap.save(str(destination), "JPG", 84):
            return None
        return destination

    @staticmethod
    def _is_foreground(window_id: int) -> bool:
        if not hasattr(ctypes, "windll"):
            return False
        user32 = ctypes.windll.user32
        return bool(
            not user32.IsIconic(window_id)
            and int(user32.GetForegroundWindow()) == window_id
        )

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
        bounds = cls._game_window_bounds(process_names)
        return bounds[0] if bounds is not None else None

    @classmethod
    def _game_window_bounds(
        cls,
        process_names: list[str],
    ) -> tuple[int, int, int, int, int] | None:
        process_ids = cls._process_ids(process_names)
        if not process_ids or not hasattr(ctypes, "WINFUNCTYPE"):
            return None
        user32 = ctypes.windll.user32
        candidates: list[tuple[int, int, int, int, int, int]] = []
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
                    candidates.append(
                        (
                            width * height,
                            int(hwnd),
                            rectangle.left,
                            rectangle.top,
                            width,
                            height,
                        )
                    )
            return True

        user32.EnumWindows(visit, 0)
        if not candidates:
            return None
        _area, hwnd, left, top, width, height = max(candidates)
        return hwnd, left, top, width, height
