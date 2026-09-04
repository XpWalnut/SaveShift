from pathlib import Path
from typing import Protocol

from app.package_transport.models import PackageArtifact, PackageDescriptor


class PackageBlobTransport(Protocol):
    """Low-level provider for opaque encrypted package payloads."""

    @property
    def name(self) -> str:
        ...

    def publish_blob(
        self,
        payload_path: Path,
        descriptor: PackageDescriptor,
    ) -> PackageArtifact:
        ...

    def download_blob(
        self,
        artifact: PackageArtifact,
        destination_path: Path,
    ) -> None:
        ...

    def delete(self, artifact: PackageArtifact) -> None:
        ...
