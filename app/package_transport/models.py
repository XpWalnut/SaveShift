from dataclasses import dataclass


@dataclass(frozen=True)
class PackageDescriptor:
    """Provider-independent identity of one immutable ``.sspkg`` version."""

    project_uuid: str
    project_version: int
    package_checksum: str
    package_size_bytes: int


@dataclass(frozen=True)
class PackageArtifact:
    """A package descriptor plus the provider locator needed to retrieve it."""

    transport_name: str
    remote_id: str
    project_uuid: str
    project_version: int
    package_checksum: str
    package_size_bytes: int
    encryption_key_id: str | None = None

    @property
    def descriptor(self) -> PackageDescriptor:
        return PackageDescriptor(
            project_uuid=self.project_uuid,
            project_version=self.project_version,
            package_checksum=self.package_checksum,
            package_size_bytes=self.package_size_bytes,
        )
