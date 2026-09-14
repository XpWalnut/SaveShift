from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import uuid

from app.core.config import AppConfig
from app.steam.group_manifest import SteamGroupManifest


@dataclass(frozen=True)
class CachedSteamGroupManifest:
    manifest_item_id: str
    manifest: SteamGroupManifest
    cached_at_utc: str


class SteamGroupManifestCache:
    """Keeps a last-known verified manifest for recovery, never coordination."""

    SCHEMA_VERSION = 1

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or (
            AppConfig.get_data_directory() / "steam-group-manifests"
        )

    def save(
        self,
        manifest_item_id: str,
        manifest: SteamGroupManifest,
    ) -> CachedSteamGroupManifest:
        item_id = self._item_id(manifest_item_id)
        if not manifest.verify():
            raise ValueError("Only a verified Steam group manifest can be cached.")
        cached_at = datetime.now(UTC).isoformat()
        value = {
            "schema_version": self.SCHEMA_VERSION,
            "manifest_item_id": item_id,
            "cached_at_utc": cached_at,
            "manifest": json.loads(manifest.to_json()),
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(manifest.group_id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return CachedSteamGroupManifest(item_id, manifest, cached_at)

    def load(
        self,
        group_id: str,
        *,
        expected_manifest_item_id: str | None = None,
    ) -> CachedSteamGroupManifest | None:
        path = self._path(group_id)
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("schema_version") != self.SCHEMA_VERSION:
                raise ValueError("unsupported cache schema")
            item_id = self._item_id(value["manifest_item_id"])
            if (
                expected_manifest_item_id is not None
                and item_id != self._item_id(expected_manifest_item_id)
            ):
                raise ValueError("cached manifest item does not match settings")
            manifest = SteamGroupManifest.from_json(
                json.dumps(value["manifest"])
            )
            if manifest.group_id != str(uuid.UUID(group_id)):
                raise ValueError("cached manifest belongs to another group")
            cached_at = str(value["cached_at_utc"])
            timestamp = datetime.fromisoformat(cached_at)
            if timestamp.tzinfo is None:
                raise ValueError("cache timestamp has no timezone")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("The cached Steam group manifest is invalid.") from error
        return CachedSteamGroupManifest(item_id, manifest, cached_at)

    def remove(self, group_id: str) -> None:
        self._path(group_id).unlink(missing_ok=True)

    def _path(self, group_id: str) -> Path:
        return self.directory / f"{uuid.UUID(group_id)}.json"

    @staticmethod
    def _item_id(value: object) -> str:
        normalized = str(value).strip()
        if not normalized.isdigit() or int(normalized) < 1:
            raise ValueError("The Steam manifest item identifier is invalid.")
        return normalized
