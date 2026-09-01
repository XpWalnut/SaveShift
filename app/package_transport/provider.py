from pathlib import Path
from typing import Protocol

from app.package_transport.models import PackageArtifact, PackageDescriptor


class PackageTransport(Protocol):
    """Storage boundary for immutable Save Shift package artifacts.

    Implementations may encrypt packages internally, but ``download`` must
    reproduce the original ``.sspkg`` bytes so the application can perform its
    normal package and checksum verification.
    """

    @property
    def name(self) -> str:
        """Return the stable provider name stored with remote artifacts."""

    def publish(
        self,
        package_path: Path,
        descriptor: PackageDescriptor,
    ) -> PackageArtifact:
        """Publish one immutable package and return its remote locator."""

    def download(
        self,
        artifact: PackageArtifact,
        destination_path: Path,
    ) -> None:
        """Download the original package bytes to ``destination_path``."""

    def delete(self, artifact: PackageArtifact) -> None:
        """Remove a previously published package when retention permits."""
