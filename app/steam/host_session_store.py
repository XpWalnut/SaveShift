from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import uuid

from app.core.config import AppConfig


@dataclass(frozen=True)
class SteamHostSessionCheckpoint:
    schema_version: int
    group_id: str
    project_uuid: str
    parent_descriptor_hash: str
    host_display_name: str
    started_at_utc: str

    SCHEMA_VERSION = 1

    @classmethod
    def create(
        cls,
        *,
        group_id: str,
        project_uuid: str,
        parent_descriptor_hash: str,
        host_display_name: str,
    ) -> "SteamHostSessionCheckpoint":
        parent = parent_descriptor_hash.strip().lower()
        if parent and (
            len(parent) != 64
            or any(character not in "0123456789abcdef" for character in parent)
        ):
            raise ValueError("A host checkpoint has an invalid package parent.")
        name = " ".join(host_display_name.split()).strip()
        if not name:
            raise ValueError("A host checkpoint requires a display name.")
        return cls(
            schema_version=cls.SCHEMA_VERSION,
            group_id=str(uuid.UUID(group_id)),
            project_uuid=str(uuid.UUID(project_uuid)),
            parent_descriptor_hash=parent,
            host_display_name=name,
            started_at_utc=datetime.now(UTC).isoformat(),
        )


class SteamHostSessionStore:
    """Persists enough ancestry state to recover an interrupted host safely."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or (
            AppConfig.get_data_directory() / "steam-host-sessions"
        )

    def save(
        self,
        checkpoint: SteamHostSessionCheckpoint,
    ) -> SteamHostSessionCheckpoint:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(checkpoint.project_uuid)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(checkpoint), indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return checkpoint

    def load_all(self) -> dict[str, SteamHostSessionCheckpoint]:
        if not self.directory.is_dir():
            return {}
        checkpoints: dict[str, SteamHostSessionCheckpoint] = {}
        for path in self.directory.glob("*.json"):
            checkpoint = self._load(path)
            checkpoints[checkpoint.project_uuid] = checkpoint
        return checkpoints

    def remove(self, project_uuid: str) -> None:
        self._path(project_uuid).unlink(missing_ok=True)

    def _load(self, path: Path) -> SteamHostSessionCheckpoint:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            checkpoint = SteamHostSessionCheckpoint(
                schema_version=int(value["schema_version"]),
                group_id=str(uuid.UUID(str(value["group_id"]))),
                project_uuid=str(uuid.UUID(str(value["project_uuid"]))),
                parent_descriptor_hash=str(value["parent_descriptor_hash"]),
                host_display_name=str(value["host_display_name"]),
                started_at_utc=str(value["started_at_utc"]),
            )
            if checkpoint.schema_version != checkpoint.SCHEMA_VERSION:
                raise ValueError("unsupported checkpoint schema")
            recreated = SteamHostSessionCheckpoint.create(
                group_id=checkpoint.group_id,
                project_uuid=checkpoint.project_uuid,
                parent_descriptor_hash=checkpoint.parent_descriptor_hash,
                host_display_name=checkpoint.host_display_name,
            )
            timestamp = datetime.fromisoformat(checkpoint.started_at_utc)
            if timestamp.tzinfo is None:
                raise ValueError("checkpoint timestamp has no timezone")
            if path.stem != recreated.project_uuid:
                raise ValueError("checkpoint filename does not match project")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"The Steam host checkpoint is invalid: {path.name}") from error
        return checkpoint

    def _path(self, project_uuid: str) -> Path:
        return self.directory / f"{uuid.UUID(project_uuid)}.json"
