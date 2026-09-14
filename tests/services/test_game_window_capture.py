from pathlib import Path

from PySide6.QtCore import QRect

from app.services.game_window_capture import GameWindowCapture


def test_game_capture_reads_live_screen_region_instead_of_window_surface(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = []
    destination = tmp_path / "capture.jpg"

    class Pixmap:
        def isNull(self):
            return False

        def width(self):
            return 1280

        def height(self):
            return 720

        def save(self, path, _format, _quality):
            Path(path).write_bytes(b"live frame")
            return True

    class Screen:
        def geometry(self):
            return QRect(1920, 0, 1920, 1080)

        def grabWindow(self, *arguments):
            calls.append(arguments)
            return Pixmap()

    class Application:
        @staticmethod
        def screenAt(_point):
            return Screen()

        @staticmethod
        def primaryScreen():
            raise AssertionError("The matching monitor should be used")

    monkeypatch.setattr(
        GameWindowCapture,
        "_game_window_bounds",
        lambda _names: (42, 2020, 100, 1280, 720),
    )
    monkeypatch.setattr(GameWindowCapture, "_is_foreground", lambda _hwnd: True)
    monkeypatch.setattr(
        "app.services.game_window_capture.QGuiApplication",
        Application,
    )

    assert GameWindowCapture.capture(["game.exe"], destination) == destination
    assert calls == [(0, 100, 100, 1280, 720)]
    assert destination.read_bytes() == b"live frame"
