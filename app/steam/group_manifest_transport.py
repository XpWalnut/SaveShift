import json
import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from app.core.config import AppConfig
from app.steam.constants import SAVESHIFT_STEAM_APP_ID
from app.steam.group_manifest import SteamGroupManifest
from app.steam.ugc_client import SteamUgcClient, SteamUgcVisibility


class SteamGroupManifestTransport:
    """Stores each group's signed manifest in one stable unlisted UGC item."""

    FILE_NAME = "saveshift-group-manifest.json"

    def __init__(
        self,
        client: SteamUgcClient,
        temporary_directory: Path | None = None,
        on_legal_agreement_required: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.temporary_directory = temporary_directory
        self.on_legal_agreement_required = on_legal_agreement_required

    def publish(self, manifest: SteamGroupManifest) -> str:
        content = self._content_directory(manifest)
        try:
            result = self.client.publish_item(
                content,
                title=f"Save Shift Group: {manifest.name}",
                description="Signed Save Shift group manifest.",
                metadata=self._metadata(manifest),
                visibility=SteamUgcVisibility.UNLISTED,
            )
            self._notify_legal_agreement(
                result.published_file_id,
                result.user_needs_legal_agreement,
            )
            return self._item_id(result.published_file_id)
        finally:
            shutil.rmtree(content, ignore_errors=True)

    def update(self, manifest_item_id: str, manifest: SteamGroupManifest) -> None:
        item_id = self._item_id(manifest_item_id)
        content = self._content_directory(manifest)
        try:
            result = self.client.update_item(
                item_id,
                content,
                title=f"Save Shift Group: {manifest.name}",
                description="Signed Save Shift group manifest.",
                metadata=self._metadata(manifest),
                visibility=SteamUgcVisibility.UNLISTED,
            )
            if self._item_id(result.published_file_id) != item_id:
                raise ValueError("Steam updated a different group manifest item.")
            self._notify_legal_agreement(
                item_id,
                result.user_needs_legal_agreement,
            )
        finally:
            shutil.rmtree(content, ignore_errors=True)

    def download(self, manifest_item_id: str) -> SteamGroupManifest:
        content = self.client.download_item(self._item_id(manifest_item_id))
        path = content / self.FILE_NAME
        if not path.is_file():
            raise ValueError("The Steam item does not contain a group manifest.")
        return SteamGroupManifest.from_json(path.read_text(encoding="utf-8"))

    def _content_directory(self, manifest: SteamGroupManifest) -> Path:
        root = self.temporary_directory or (
            AppConfig.get_temp_directory() / "steam-group-manifests"
        )
        root.mkdir(parents=True, exist_ok=True)
        content = root / f"manifest-{uuid4().hex}"
        content.mkdir()
        (content / self.FILE_NAME).write_text(
            manifest.to_json(),
            encoding="utf-8",
        )
        return content

    @staticmethod
    def _metadata(manifest: SteamGroupManifest) -> str:
        return json.dumps(
            {
                "schema": 1,
                "kind": "saveshift-group-manifest",
                "app_id": SAVESHIFT_STEAM_APP_ID,
                "group_id": manifest.group_id,
                "revision": manifest.revision,
                "key_epoch": manifest.key_epoch,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _notify_legal_agreement(self, item_id: str, required: bool) -> None:
        if required and self.on_legal_agreement_required is not None:
            self.on_legal_agreement_required(
                f"steam://url/CommunityFilePage/{item_id}"
            )

    @staticmethod
    def _item_id(value: str) -> str:
        normalized = str(value).strip()
        if not normalized.isdigit() or int(normalized) < 1:
            raise ValueError("The Steam group manifest item identifier is invalid.")
        return normalized
