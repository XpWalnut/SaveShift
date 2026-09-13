import json
import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from app.core.config import AppConfig
from app.steam.device_identity import SteamDeviceIdentity
from app.steam.package_index import SteamMemberPackageIndex
from app.steam.ugc_client import SteamUgcClient, SteamUgcVisibility


class SteamMemberPackageIndexTransport:
    FILE_NAME = "saveshift-member-package-index.json"

    def __init__(
        self,
        client: SteamUgcClient,
        temporary_directory: Path | None = None,
        on_legal_agreement_required: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.temporary_directory = temporary_directory
        self.on_legal_agreement_required = on_legal_agreement_required

    def publish(
        self,
        *,
        group_id: str,
        publisher: SteamDeviceIdentity,
    ) -> SteamMemberPackageIndex:
        bootstrap = self._directory()
        try:
            (bootstrap / self.FILE_NAME).write_text("{}\n", encoding="utf-8")
            result = self.client.publish_item(
                bootstrap,
                title="Save Shift Package Index",
                description="Signed index for encrypted Save Shift packages.",
                metadata='{"kind":"saveshift-member-package-index-pending"}',
                visibility=SteamUgcVisibility.UNLISTED,
            )
            self._notify(result.published_file_id, result.user_needs_legal_agreement)
            index = SteamMemberPackageIndex.create(
                group_id=group_id,
                publisher=publisher,
                workshop_item_id=result.published_file_id,
            )
            self.update(index)
            return index
        finally:
            shutil.rmtree(bootstrap, ignore_errors=True)

    def update(self, index: SteamMemberPackageIndex) -> None:
        content = self._directory()
        try:
            (content / self.FILE_NAME).write_text(index.to_json(), encoding="utf-8")
            result = self.client.update_item(
                index.workshop_item_id,
                content,
                title="Save Shift Package Index",
                description="Signed index for encrypted Save Shift packages.",
                metadata=self._metadata(index),
                visibility=SteamUgcVisibility.UNLISTED,
            )
            if result.published_file_id != index.workshop_item_id:
                raise ValueError("Steam updated a different package-index item.")
            self._notify(index.workshop_item_id, result.user_needs_legal_agreement)
        finally:
            shutil.rmtree(content, ignore_errors=True)

    def download(self, workshop_item_id: str) -> SteamMemberPackageIndex:
        content = self.client.download_item(workshop_item_id)
        path = content / self.FILE_NAME
        if not path.is_file():
            raise ValueError("The Workshop item has no member package index.")
        return SteamMemberPackageIndex.from_json(path.read_text(encoding="utf-8"))

    def _directory(self) -> Path:
        root = self.temporary_directory or (
            AppConfig.get_temp_directory() / "steam-package-indexes"
        )
        root.mkdir(parents=True, exist_ok=True)
        content = root / f"index-{uuid4().hex}"
        content.mkdir()
        return content

    def _notify(self, item_id: str, required: bool) -> None:
        if required and self.on_legal_agreement_required is not None:
            self.on_legal_agreement_required(f"steam://url/CommunityFilePage/{item_id}")

    @staticmethod
    def _metadata(index: SteamMemberPackageIndex) -> str:
        return json.dumps(
            {
                "kind": SteamMemberPackageIndex.METADATA_KIND,
                "group_id": index.group_id,
                "publisher_device_id": index.publisher_device_id,
                "revision": index.revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
