from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from app.coordination.provider import PackageKeyProvider
from app.core.config import AppConfig
from app.package_transport.blob_provider import PackageBlobTransport
from app.package_transport.encryption import PackageEncryption
from app.package_transport.errors import PackageEncryptionError
from app.package_transport.models import PackageArtifact, PackageDescriptor


class EncryptedPackageTransport:
    """Adds group-authenticated encryption to an opaque blob transport."""

    def __init__(
        self,
        blob_transport: PackageBlobTransport,
        key_provider: PackageKeyProvider,
        temporary_directory: Path | None = None,
    ) -> None:
        self.blob_transport = blob_transport
        self.key_provider = key_provider
        self.temporary_directory = temporary_directory

    @property
    def name(self) -> str:
        return self.blob_transport.name

    def publish(
        self,
        package_path: Path,
        descriptor: PackageDescriptor,
    ) -> PackageArtifact:
        encrypted_path = self._temporary_path()

        try:
            key = self.key_provider.get_package_encryption_key()
            PackageEncryption.encrypt(
                package_path,
                encrypted_path,
                key.key_material,
            )
            artifact = self.blob_transport.publish_blob(
                encrypted_path,
                descriptor,
            )
            return replace(artifact, encryption_key_id=key.key_id)
        finally:
            self._remove_temporary(encrypted_path)

    def download(
        self,
        artifact: PackageArtifact,
        destination_path: Path,
    ) -> None:
        encrypted_path = self._temporary_path()

        try:
            self.blob_transport.download_blob(artifact, encrypted_path)
            if not artifact.encryption_key_id:
                raise PackageEncryptionError(
                    "The remote package does not identify its encryption key."
                )

            key = self.key_provider.get_package_encryption_key(
                artifact.encryption_key_id
            )
            PackageEncryption.decrypt(
                encrypted_path,
                destination_path,
                key.key_material,
            )
        finally:
            self._remove_temporary(encrypted_path)

    def delete(self, artifact: PackageArtifact) -> None:
        self.blob_transport.delete(artifact)

    def _temporary_path(self) -> Path:
        directory = self.temporary_directory or AppConfig.get_temp_directory()
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"package-{uuid4().hex}.ssenc"

    @staticmethod
    def _remove_temporary(path: Path) -> None:
        if path.is_file() or path.is_symlink():
            path.unlink()
