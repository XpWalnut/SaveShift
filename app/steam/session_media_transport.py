import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

from app.core.config import AppConfig
from app.package_transport.encryption import PackageEncryption
from app.steam.session_media import SteamSessionMediaReference
from app.steam.ugc_client import SteamUgcClient, SteamUgcVisibility


class SteamSessionMediaTransport:
    """Publishes and retrieves an encrypted image tied to one save artifact."""

    FILE_NAME = "saveshift-session-image.ssenc"
    MAX_PLAINTEXT_BYTES = 25 * 1024 * 1024
    MAX_ENCRYPTED_BYTES = MAX_PLAINTEXT_BYTES + 1024

    def __init__(
        self,
        client: SteamUgcClient,
        temporary_directory: Path | None = None,
    ) -> None:
        self.client = client
        self.temporary_directory = temporary_directory

    def publish(
        self,
        *,
        image_path: Path,
        project_uuid: str,
        project_version: int,
        package_item_id: str,
        package_checksum: str,
        key_epoch: int,
        key_material: bytes,
        captured_at_utc: str,
    ) -> SteamSessionMediaReference:
        image = image_path.resolve()
        if not image.is_file():
            raise FileNotFoundError(f"Session image not found: {image}")
        if image.stat().st_size > self.MAX_PLAINTEXT_BYTES:
            raise ValueError("The session image is larger than 25 MB.")
        image_checksum = self._checksum(image)
        content = self._directory()
        try:
            PackageEncryption.encrypt(
                image,
                content / self.FILE_NAME,
                key_material,
            )
            metadata = json.dumps(
                {
                    "kind": "saveshift-session-media",
                    "project_uuid": project_uuid,
                    "project_version": project_version,
                    "package_item_id": package_item_id,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            result = self.client.publish_item(
                content,
                title="Save Shift Session Image",
                description="Encrypted session image for a Save Shift world.",
                metadata=metadata,
                visibility=SteamUgcVisibility.UNLISTED,
            )
            reference = SteamSessionMediaReference(
                project_uuid=project_uuid,
                project_version=project_version,
                package_item_id=package_item_id,
                package_checksum=package_checksum,
                media_item_id=result.published_file_id,
                image_checksum=image_checksum,
                key_epoch=key_epoch,
                captured_at_utc=captured_at_utc,
            )
            reference.validate()
            return reference
        finally:
            shutil.rmtree(content, ignore_errors=True)

    def download(
        self,
        reference: SteamSessionMediaReference,
        *,
        destination: Path,
        key_material: bytes,
    ) -> Path:
        reference.validate()
        content = self.client.download_item(reference.media_item_id)
        encrypted = content / self.FILE_NAME
        if not encrypted.is_file():
            raise ValueError("The Steam media item contains no session image.")
        if encrypted.stat().st_size > self.MAX_ENCRYPTED_BYTES:
            raise ValueError("The encrypted Steam session image is too large.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        PackageEncryption.decrypt(encrypted, destination, key_material)
        try:
            if destination.stat().st_size > self.MAX_PLAINTEXT_BYTES:
                raise ValueError("The decrypted Steam session image is too large.")
            if self._checksum(destination) != reference.image_checksum:
                raise ValueError("The Steam session image checksum does not match.")
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return destination

    def _directory(self) -> Path:
        root = self.temporary_directory or (
            AppConfig.get_temp_directory() / "steam-session-media"
        )
        root.mkdir(parents=True, exist_ok=True)
        content = root / f"media-{uuid4().hex}"
        content.mkdir()
        return content

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
