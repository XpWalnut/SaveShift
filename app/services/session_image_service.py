from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import time
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader

from app.core.config import AppConfig


@dataclass(frozen=True)
class SessionImageRecord:
    project_uuid: str
    project_version: int
    captured_at_utc: str
    image_path: Path


class SessionImageService:
    """Stores a normalized, metadata-free image for a world's latest session."""

    MAX_SOURCE_BYTES = 25 * 1024 * 1024
    MAX_WIDTH = 1600
    MAX_HEIGHT = 900

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or (
            AppConfig.get_data_directory() / "session-images"
        )

    def select(
        self,
        *,
        project_uuid: str,
        project_version: int,
        source_path: Path,
    ) -> SessionImageRecord:
        project_id = str(uuid.UUID(project_uuid))
        if project_version < 1:
            raise ValueError("A session image requires a valid project version.")
        source = source_path.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Session image not found: {source}")
        if source.stat().st_size > self.MAX_SOURCE_BYTES:
            raise ValueError("The selected session image is larger than 25 MB.")
        reader = QImageReader(str(source))
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            raise ValueError("The selected file is not a supported image.")
        image = self._scaled(image)
        project_directory = self.directory / project_id
        project_directory.mkdir(parents=True, exist_ok=True)
        image_path = project_directory / "latest.jpg"
        temporary_image = project_directory / "latest.tmp.jpg"
        if not image.save(str(temporary_image), "JPG", 88):
            raise OSError("Save Shift could not encode the session image.")
        temporary_image.replace(image_path)
        record = SessionImageRecord(
            project_uuid=project_id,
            project_version=project_version,
            captured_at_utc=datetime.now(UTC).isoformat(),
            image_path=image_path,
        )
        temporary_metadata = project_directory / "latest.tmp.json"
        metadata_path = project_directory / "latest.json"
        value = asdict(record)
        value["image_path"] = image_path.name
        temporary_metadata.write_text(
            json.dumps(value, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_metadata.replace(metadata_path)
        return record

    def clear(self, project_uuid: str) -> None:
        project_id = str(uuid.UUID(project_uuid))
        shutil.rmtree(self.directory / project_id, ignore_errors=True)

    def candidate_path(self, project_uuid: str, index: int) -> Path:
        project_id = str(uuid.UUID(project_uuid))
        return (
            AppConfig.get_temp_directory()
            / "session-captures"
            / project_id
            / f"capture-{index}.jpg"
        )

    def clear_candidates(self, project_uuid: str) -> None:
        project_id = str(uuid.UUID(project_uuid))
        shutil.rmtree(
            AppConfig.get_temp_directory() / "session-captures" / project_id,
            ignore_errors=True,
        )

    def clear_stale_candidates(self, *, max_age_seconds: int = 24 * 60 * 60) -> None:
        """Remove abandoned temporary captures without touching selected images."""
        if max_age_seconds < 0:
            raise ValueError("Candidate maximum age cannot be negative.")
        root = AppConfig.get_temp_directory() / "session-captures"
        if not root.is_dir():
            return
        cutoff = time.time() - max_age_seconds
        for directory in root.iterdir():
            try:
                if directory.is_dir() and directory.stat().st_mtime <= cutoff:
                    shutil.rmtree(directory, ignore_errors=True)
            except OSError:
                continue

    def latest(self, project_uuid: str) -> SessionImageRecord | None:
        project_id = str(uuid.UUID(project_uuid))
        directory = self.directory / project_id
        metadata_path = directory / "latest.json"
        image_path = directory / "latest.jpg"
        if not metadata_path.is_file() or not image_path.is_file():
            return None
        try:
            value = json.loads(metadata_path.read_text(encoding="utf-8"))
            if str(uuid.UUID(str(value["project_uuid"]))) != project_id:
                raise ValueError("project mismatch")
            version = int(value["project_version"])
            timestamp = datetime.fromisoformat(str(value["captured_at_utc"]))
            if version < 1 or timestamp.tzinfo is None:
                raise ValueError("invalid session image metadata")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        return SessionImageRecord(
            project_uuid=project_id,
            project_version=version,
            captured_at_utc=timestamp.astimezone(UTC).isoformat(),
            image_path=image_path,
        )

    @classmethod
    def _scaled(cls, image: QImage) -> QImage:
        if image.width() <= cls.MAX_WIDTH and image.height() <= cls.MAX_HEIGHT:
            return image
        return image.scaled(
            cls.MAX_WIDTH,
            cls.MAX_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
