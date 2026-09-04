from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.coordination.models import (
    CatalogPackage,
    LockLease,
    PackageCatalogMetadata,
)
from app.coordination.errors import PackageKeyRotatedError
from app.package_transport.errors import PackageTransferIntegrityError
from app.package_transport.handoff_service import PackageHandoffService
from app.package_transport.models import PackageArtifact
from app.packages.checksum import calculate_sha256
from tests.package_transport.test_transfer_service import (
    PROJECT_UUID,
    MemoryTransport,
    _create_package,
)


def _lease() -> LockLease:
    return LockLease(
        project_uuid=PROJECT_UUID,
        lease_id="lease-123",
        fencing_token=1,
        owner_device_id="device-123",
        owner_display_name="Alice",
        acquired_at_utc=datetime(2026, 8, 6, 12, tzinfo=UTC),
        expires_at_utc=datetime(2026, 8, 6, 12, 15, tzinfo=UTC),
    )


class MemoryCatalog:
    def __init__(self) -> None:
        self.packages: list[CatalogPackage] = []
        self.register_error: Exception | None = None
        self.register_calls = 0
        self.transform = lambda package: package

    def register_package(
        self,
        artifact: PackageArtifact,
        lease: LockLease,
        metadata: PackageCatalogMetadata | None = None,
    ) -> CatalogPackage:
        self.register_calls += 1
        if self.register_error is not None:
            raise self.register_error

        package = self.transform(
            CatalogPackage(
                catalog_id="catalog-123",
                artifact=artifact,
                published_by_device_id=lease.owner_device_id,
                published_at_utc=datetime(2026, 8, 6, 12, tzinfo=UTC),
                metadata=metadata,
            )
        )
        self.packages.append(package)
        return package

    def list_packages(self, project_uuid: str) -> list[CatalogPackage]:
        return list(self.packages)


def test_publish_registers_transport_artifact_in_group_catalog(
    tmp_path: Path,
) -> None:
    package_path = _create_package(tmp_path)
    transport = MemoryTransport()
    catalog = MemoryCatalog()

    published = PackageHandoffService.publish(
        package_path,
        _lease(),
        transport,
        catalog,
    )

    assert published == catalog.packages[0]
    assert published.artifact.package_checksum == calculate_sha256(package_path)
    assert published.artifact.remote_id in transport.payloads
    assert published.metadata is not None
    assert published.metadata.project_name == "Shared World"


def test_publish_deletes_remote_artifact_when_catalog_registration_fails(
    tmp_path: Path,
) -> None:
    transport = MemoryTransport()
    catalog = MemoryCatalog()
    catalog.register_error = RuntimeError("catalog offline")

    with pytest.raises(RuntimeError, match="catalog offline"):
        PackageHandoffService.publish(
            _create_package(tmp_path),
            _lease(),
            transport,
            catalog,
        )

    assert transport.payloads == {}
    assert transport.delete_calls == 1


def test_publish_retries_once_when_group_key_rotates(
    tmp_path: Path,
) -> None:
    transport = MemoryTransport()
    catalog = MemoryCatalog()
    original_register = catalog.register_package

    def rotate_once(
        artifact: PackageArtifact,
        lease: LockLease,
        metadata: PackageCatalogMetadata | None = None,
    ) -> CatalogPackage:
        if catalog.register_calls == 0:
            catalog.register_calls += 1
            raise PackageKeyRotatedError("key rotated")
        return original_register(artifact, lease, metadata)

    catalog.register_package = rotate_once

    published = PackageHandoffService.publish(
        _create_package(tmp_path),
        _lease(),
        transport,
        catalog,
    )

    assert published.artifact.remote_id in transport.payloads
    assert catalog.register_calls == 2
    assert transport.delete_calls == 1


def test_publish_rejects_and_removes_catalog_metadata_mutation(
    tmp_path: Path,
) -> None:
    transport = MemoryTransport()
    catalog = MemoryCatalog()

    def change_artifact(package: CatalogPackage) -> CatalogPackage:
        changed = PackageArtifact(
            transport_name=package.artifact.transport_name,
            remote_id=package.artifact.remote_id,
            project_uuid=package.artifact.project_uuid,
            project_version=999,
            package_checksum=package.artifact.package_checksum,
            package_size_bytes=package.artifact.package_size_bytes,
        )
        return CatalogPackage(
            catalog_id=package.catalog_id,
            artifact=changed,
            published_by_device_id=package.published_by_device_id,
            published_at_utc=package.published_at_utc,
        )

    catalog.transform = change_artifact

    with pytest.raises(PackageTransferIntegrityError):
        PackageHandoffService.publish(
            _create_package(tmp_path),
            _lease(),
            transport,
            catalog,
        )

    assert transport.payloads == {}


def test_download_latest_uses_highest_catalog_version(
    tmp_path: Path,
) -> None:
    transport = MemoryTransport()
    catalog = MemoryCatalog()
    older_path = _create_package(tmp_path / "older", version=2)
    newer_path = _create_package(tmp_path / "newer", version=5)
    older = PackageHandoffService.publish(
        older_path,
        _lease(),
        transport,
        catalog,
    )
    transport.payloads["artifact-2"] = newer_path.read_bytes()
    newer_artifact = PackageArtifact(
        transport_name=transport.name,
        remote_id="artifact-2",
        project_uuid=PROJECT_UUID,
        project_version=5,
        package_checksum=calculate_sha256(newer_path),
        package_size_bytes=newer_path.stat().st_size,
    )
    newer = catalog.register_package(newer_artifact, _lease())
    catalog.packages = [newer, older]

    result = PackageHandoffService.download_latest(
        PROJECT_UUID,
        tmp_path / "downloaded.sspkg",
        transport,
        catalog,
    )

    assert result is not None
    package, downloaded_path = result
    assert package is newer
    assert downloaded_path.read_bytes() == newer_path.read_bytes()


def test_download_latest_returns_none_for_empty_catalog(tmp_path: Path) -> None:
    result = PackageHandoffService.download_latest(
        PROJECT_UUID,
        tmp_path / "downloaded.sspkg",
        MemoryTransport(),
        MemoryCatalog(),
    )

    assert result is None
