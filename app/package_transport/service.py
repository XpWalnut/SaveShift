from pathlib import Path
from uuid import uuid4

from app.package_transport.errors import (
    PackageTransferIntegrityError,
    PackageTransportMismatchError,
)
from app.package_transport.models import PackageArtifact, PackageDescriptor
from app.package_transport.provider import PackageTransport
from app.packages.checksum import calculate_sha256
from app.packages.package_reader import PackageReader


class PackageTransferService:
    """Verifies packages on both sides of a provider-neutral transfer."""

    @staticmethod
    def publish(
        package_path: Path,
        transport: PackageTransport,
    ) -> PackageArtifact:
        package_path = Path(package_path)
        package_info = PackageReader.read(package_path)
        descriptor = PackageDescriptor(
            project_uuid=package_info.project_uuid,
            project_version=package_info.project_version,
            package_checksum=calculate_sha256(package_path),
            package_size_bytes=package_path.stat().st_size,
        )

        artifact = transport.publish(package_path, descriptor)
        PackageTransferService._validate_published_artifact(
            artifact,
            descriptor,
            transport,
        )
        return artifact

    @staticmethod
    def download(
        artifact: PackageArtifact,
        destination_path: Path,
        transport: PackageTransport,
    ) -> Path:
        PackageTransferService._require_matching_transport(artifact, transport)
        destination_path = Path(destination_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = destination_path.parent / (
            f".{destination_path.name}.{uuid4().hex}.part"
        )

        try:
            transport.download(artifact, temporary_path)
            PackageTransferService._verify_download(temporary_path, artifact)
            temporary_path.replace(destination_path)
        finally:
            if temporary_path.is_file() or temporary_path.is_symlink():
                temporary_path.unlink()

        return destination_path

    @staticmethod
    def delete(
        artifact: PackageArtifact,
        transport: PackageTransport,
    ) -> None:
        PackageTransferService._require_matching_transport(artifact, transport)
        transport.delete(artifact)

    @staticmethod
    def _validate_published_artifact(
        artifact: PackageArtifact,
        descriptor: PackageDescriptor,
        transport: PackageTransport,
    ) -> None:
        if not artifact.remote_id.strip():
            raise PackageTransferIntegrityError(
                "The package transport returned an empty remote identifier."
            )

        if artifact.transport_name != transport.name:
            raise PackageTransferIntegrityError(
                "The package transport returned the wrong provider name."
            )

        if artifact.descriptor != descriptor:
            raise PackageTransferIntegrityError(
                "The package transport changed the published package metadata."
            )

    @staticmethod
    def _require_matching_transport(
        artifact: PackageArtifact,
        transport: PackageTransport,
    ) -> None:
        if artifact.transport_name != transport.name:
            raise PackageTransportMismatchError(
                f"Package {artifact.remote_id} belongs to "
                f"{artifact.transport_name}, not {transport.name}."
            )

    @staticmethod
    def _verify_download(
        package_path: Path,
        artifact: PackageArtifact,
    ) -> None:
        if not package_path.is_file():
            raise PackageTransferIntegrityError(
                "The package transport did not produce a downloaded file."
            )

        if package_path.stat().st_size != artifact.package_size_bytes:
            raise PackageTransferIntegrityError(
                "The downloaded package size does not match the published package."
            )

        if calculate_sha256(package_path) != artifact.package_checksum:
            raise PackageTransferIntegrityError(
                "The downloaded package checksum does not match the published package."
            )

        try:
            package_info = PackageReader.read(package_path)
        except (OSError, ValueError, KeyError) as error:
            raise PackageTransferIntegrityError(
                "The downloaded package failed Save Shift verification."
            ) from error

        if (
            package_info.project_uuid != artifact.project_uuid
            or package_info.project_version != artifact.project_version
        ):
            raise PackageTransferIntegrityError(
                "The downloaded package identity does not match the published package."
            )
