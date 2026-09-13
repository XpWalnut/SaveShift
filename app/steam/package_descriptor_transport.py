import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from app.core.config import AppConfig
from app.package_transport.models import PackageArtifact
from app.packages.checksum import calculate_sha256
from app.steam.constants import STEAM_UGC_PAYLOAD_NAME
from app.steam.device_identity import SteamDeviceIdentity
from app.steam.group_manifest import SteamGroupManifest
from app.steam.package_descriptor import SteamPackageDescriptor
from app.steam.ugc_client import SteamUgcClient, SteamUgcVisibility


class SteamPackageDescriptorTransport:
    """Attaches a signed descriptor to an already encrypted Workshop package."""

    FILE_NAME = "saveshift-package-descriptor.json"

    def __init__(
        self,
        client: SteamUgcClient,
        temporary_directory: Path | None = None,
        on_legal_agreement_required: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.temporary_directory = temporary_directory
        self.on_legal_agreement_required = on_legal_agreement_required

    def attach(
        self,
        artifact: PackageArtifact,
        *,
        manifest: SteamGroupManifest,
        publisher: SteamDeviceIdentity,
        parent_descriptor_hash: str | None,
        project_name: str,
        game_id: str,
        created_by: str,
    ) -> SteamPackageDescriptor:
        source = self.client.download_item(artifact.remote_id)
        payload = source / STEAM_UGC_PAYLOAD_NAME
        if not payload.is_file():
            raise ValueError("The Workshop package has no encrypted payload.")
        content = self._temporary_path()
        content.mkdir(parents=True)
        try:
            shutil.copy2(payload, content / STEAM_UGC_PAYLOAD_NAME)
            descriptor = SteamPackageDescriptor.create(
                manifest=manifest,
                publisher=publisher,
                project_uuid=artifact.project_uuid,
                project_version=artifact.project_version,
                parent_descriptor_hash=parent_descriptor_hash,
                encrypted_payload_checksum=calculate_sha256(payload),
                package_checksum=artifact.package_checksum,
                package_size_bytes=artifact.package_size_bytes,
                workshop_item_id=artifact.remote_id,
                project_name=project_name,
                game_id=game_id,
                created_by=created_by,
            )
            (content / self.FILE_NAME).write_text(
                descriptor.to_json(), encoding="utf-8"
            )
            metadata = descriptor.to_json(compact=True)
            if len(metadata.encode("utf-8")) > 5000:
                raise ValueError("The signed Steam package descriptor is too large.")
            result = self.client.update_item(
                artifact.remote_id,
                content,
                title=f"Save Shift {project_name} v{artifact.project_version}",
                description="Encrypted Save Shift group package.",
                metadata=metadata,
                visibility=SteamUgcVisibility.UNLISTED,
            )
            if result.published_file_id != artifact.remote_id:
                raise ValueError("Steam updated a different package item.")
            if result.user_needs_legal_agreement:
                self._notify_legal_agreement(artifact.remote_id)
            return descriptor
        finally:
            shutil.rmtree(content, ignore_errors=True)

    def read(self, workshop_item_id: str) -> SteamPackageDescriptor:
        content = self.client.download_item(workshop_item_id)
        path = content / self.FILE_NAME
        if not path.is_file():
            raise ValueError("The Workshop item has no signed package descriptor.")
        return SteamPackageDescriptor.from_json(path.read_text(encoding="utf-8"))

    def _temporary_path(self) -> Path:
        root = self.temporary_directory or (
            AppConfig.get_temp_directory() / "steam-package-descriptors"
        )
        root.mkdir(parents=True, exist_ok=True)
        return root / f"descriptor-{uuid4().hex}"

    def _notify_legal_agreement(self, item_id: str) -> None:
        if self.on_legal_agreement_required is not None:
            self.on_legal_agreement_required(
                f"steam://url/CommunityFilePage/{item_id}"
            )
