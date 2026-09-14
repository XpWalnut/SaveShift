from pathlib import Path
import os
import time

from PySide6.QtGui import QColor, QImage

from app.services.session_image_service import SessionImageService


PROJECT_ID = "12345678-1234-4678-9234-567812345678"


def _image(path: Path, width: int = 1920, height: int = 1080) -> Path:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#614A8E"))
    assert image.save(str(path), "PNG")
    return path


def test_session_image_is_normalized_loaded_and_cleared(tmp_path: Path) -> None:
    service = SessionImageService(tmp_path / "images")
    source = _image(tmp_path / "source.png")

    record = service.select(
        project_uuid=PROJECT_ID,
        project_version=7,
        source_path=source,
    )

    assert record.image_path.suffix == ".jpg"
    assert record.image_path.is_file()
    stored = QImage(str(record.image_path))
    assert stored.width() <= service.MAX_WIDTH
    assert stored.height() <= service.MAX_HEIGHT
    assert service.latest(PROJECT_ID) == record

    service.clear(PROJECT_ID)
    assert service.latest(PROJECT_ID) is None


def test_session_image_rejects_non_image_input(tmp_path: Path) -> None:
    service = SessionImageService(tmp_path / "images")
    source = tmp_path / "notes.txt"
    source.write_text("not an image", encoding="utf-8")

    try:
        service.select(
            project_uuid=PROJECT_ID,
            project_version=1,
            source_path=source,
        )
    except ValueError as error:
        assert "not a supported image" in str(error)
    else:
        raise AssertionError("Non-image input was accepted")


def test_stale_capture_cleanup_preserves_recent_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.session_image_service.AppConfig.get_temp_directory",
        lambda: tmp_path,
    )
    service = SessionImageService(tmp_path / "selected")
    stale = service.candidate_path(PROJECT_ID, 1)
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"old")
    old = time.time() - 100
    os.utime(stale.parent, (old, old))

    recent_project = "22345678-1234-4678-9234-567812345678"
    recent = service.candidate_path(recent_project, 1)
    recent.parent.mkdir(parents=True)
    recent.write_bytes(b"new")

    service.clear_stale_candidates(max_age_seconds=60)

    assert not stale.parent.exists()
    assert recent.is_file()
