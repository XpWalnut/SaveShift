import json
import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from app.core.config import AppConfig
from app.package_transport.errors import PackageTransportError
from app.package_transport.models import PackageArtifact, PackageDescriptor
from app.steam.constants import (
    SAVESHIFT_STEAM_APP_ID,
    STEAM_UGC_PAYLOAD_NAME,
    STEAM_UGC_TRANSPORT_NAME,
)
from app.steam.ugc_client import SteamUgcClient, SteamUgcVisibility


class SteamUgcBlobTransport:
    """Stores opaque encrypted package payloads as unlisted Steam UGC."""

    name = STEAM_UGC_TRANSPORT_NAME

    def __init__(
        self,
        client: SteamUgcClient,
        temporary_directory: Path | None = None,
        on_legal_agreement_required: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.temporary_directory = temporary_directory
        self.on_legal_agreement_required = on_legal_agreement_required

    def publish_blob(
        self,
        payload_path: Path,
        descriptor: PackageDescriptor,
    ) -> PackageArtifact:
        if not payload_path.is_file():
            raise FileNotFoundError(f"Encrypted payload does not exist: {payload_path}")

        content_directory = self._temporary_path("upload")
        content_directory.mkdir(parents=True)

        try:
            shutil.copy2(payload_path, content_directory / STEAM_UGC_PAYLOAD_NAME)
            result = self.client.publish_item(
                content_directory,
                title=(
                    f"Save Shift {descriptor.project_uuid} "
                    f"v{descriptor.project_version}"
                ),
                description="Encrypted Save Shift group package.",
                metadata=self._metadata(descriptor),
                visibility=SteamUgcVisibility.UNLISTED,
            )
            remote_id = self._validate_remote_id(result.published_file_id)

            if result.user_needs_legal_agreement:
                self._notify_legal_agreement(remote_id)

            return PackageArtifact(
                transport_name=self.name,
                remote_id=remote_id,
                project_uuid=descriptor.project_uuid,
                project_version=descriptor.project_version,
                package_checksum=descriptor.package_checksum,
                package_size_bytes=descriptor.package_size_bytes,
            )
        finally:
            shutil.rmtree(content_directory, ignore_errors=True)

    def download_blob(
        self,
        artifact: PackageArtifact,
        destination_path: Path,
    ) -> None:
        remote_id = self._validate_remote_id(artifact.remote_id)
        content_directory = self.client.download_item(remote_id)

        if not content_directory.is_dir():
            raise PackageTransportError(
                "Steam did not return an installed directory for the package."
            )

        payload_path = content_directory / STEAM_UGC_PAYLOAD_NAME

        if not payload_path.is_file():
            raise PackageTransportError(
                "The Steam package item does not contain its encrypted payload."
            )

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(payload_path, destination_path)

    def delete(self, artifact: PackageArtifact) -> None:
        self.client.delete_item(self._validate_remote_id(artifact.remote_id))

    def _temporary_path(self, operation: str) -> Path:
        root = self.temporary_directory or (
            AppConfig.get_temp_directory() / "steam-ugc"
        )
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{operation}-{uuid4().hex}"

    def _notify_legal_agreement(self, remote_id: str) -> None:
        if self.on_legal_agreement_required is not None:
            self.on_legal_agreement_required(
                f"steam://url/CommunityFilePage/{remote_id}"
            )

    @staticmethod
    def _validate_remote_id(remote_id: str) -> str:
        normalized = str(remote_id).strip()

        if not normalized.isdigit() or int(normalized) < 1:
            raise PackageTransportError(
                "Steam returned an invalid Workshop item identifier."
            )

        return normalized

    @staticmethod
    def _metadata(descriptor: PackageDescriptor) -> str:
        return json.dumps(
            {
                "schema": 1,
                "app_id": SAVESHIFT_STEAM_APP_ID,
                "project_uuid": descriptor.project_uuid,
                "project_version": descriptor.project_version,
                "package_checksum": descriptor.package_checksum,
                "package_size_bytes": descriptor.package_size_bytes,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
