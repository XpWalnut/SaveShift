from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.coordination.models import (
    CatalogPackage,
    LockLease,
    PackageCatalogMetadata,
    PackageEncryptionKey,
)
from app.core.config import AppConfig
from app.package_transport.models import PackageArtifact, PackageDescriptor
from app.services.group_handoff_service import GroupHandoffService
from app.steam.constants import STEAM_UGC_PAYLOAD_NAME
from app.steam.ugc_client import SteamPublishedItem, SteamUgcVisibility
from tests.package_transport.test_transfer_service import _create_package


PROJECT_UUID = "12345678-1234-5678-1234-567812345678"


class MemoryGroupProvider:
    def __init__(self) -> None:
        self.packages: list[CatalogPackage] = []

    def get_package_encryption_key(
        self,
        key_id: str | None = None,
    ) -> PackageEncryptionKey:
        assert key_id is None or key_id == "key-1"
        return PackageEncryptionKey(
            key_id="key-1",
            algorithm="AES-256-GCM",
            key_material=b"k" * 32,
        )

    def register_package(
        self,
        artifact: PackageArtifact,
        lease: LockLease,
        metadata: PackageCatalogMetadata | None = None,
    ) -> CatalogPackage:
        assert lease.project_uuid == artifact.project_uuid
        package = CatalogPackage(
            catalog_id="catalog-1",
            artifact=artifact,
            published_by_device_id=lease.owner_device_id,
            published_at_utc=datetime.now(UTC),
            metadata=metadata,
        )
        self.packages.append(package)
        return package

    def list_packages(self, project_uuid: str) -> list[CatalogPackage]:
        return [
            package
            for package in self.packages
            if package.artifact.project_uuid == project_uuid
        ]


class MemorySteamClient:
    def __init__(self, payloads: dict[str, bytes], root: Path) -> None:
        self.payloads = payloads
        self.root = root
        self.closed = False

    def publish_item(
        self,
        content_directory: Path,
        *,
        title: str,
        description: str,
        metadata: str,
        visibility: SteamUgcVisibility,
    ) -> SteamPublishedItem:
        assert visibility is SteamUgcVisibility.UNLISTED
        self.payloads["9001"] = content_directory.joinpath(
            STEAM_UGC_PAYLOAD_NAME
        ).read_bytes()
        return SteamPublishedItem("9001")

    def download_item(self, published_file_id: str) -> Path:
        install_directory = self.root / f"installed-{published_file_id}"
        install_directory.mkdir(parents=True, exist_ok=True)
        install_directory.joinpath(STEAM_UGC_PAYLOAD_NAME).write_bytes(
            self.payloads[published_file_id]
        )
        return install_directory

    def delete_item(self, published_file_id: str) -> None:
        self.payloads.pop(published_file_id, None)

    def close(self) -> None:
        self.closed = True


def _lease(project_uuid: str) -> LockLease:
    now = datetime.now(UTC)
    return LockLease(
        project_uuid=project_uuid,
        lease_id="lease-1",
        fencing_token=1,
        owner_device_id="device-1",
        owner_display_name="Bob",
        acquired_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )


def test_group_handoff_round_trips_through_encrypted_steam_transport(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        AppConfig,
        "get_temp_directory",
        lambda: tmp_path / "temporary",
    )
    monkeypatch.setattr(
        AppConfig,
        "get_packages_directory",
        lambda: tmp_path / "packages",
    )
    package_path = _create_package(tmp_path)
    provider = MemoryGroupProvider()
    payloads: dict[str, bytes] = {}
    clients: list[MemorySteamClient] = []

    def client_factory() -> MemorySteamClient:
        client = MemorySteamClient(payloads, tmp_path / "steam")
        clients.append(client)
        return client

    published = GroupHandoffService.publish_package(
        package_path,
        _lease(PROJECT_UUID),
        provider,
        client_factory=client_factory,
    )
    downloaded = GroupHandoffService.download_latest(
        PROJECT_UUID,
        provider,
        client_factory=client_factory,
    )

    assert published.artifact.encryption_key_id == "key-1"
    assert payloads["9001"] != package_path.read_bytes()
    assert downloaded is not None
    catalog_package, downloaded_path = downloaded
    assert catalog_package == published
    assert downloaded_path.read_bytes() == package_path.read_bytes()
    assert all(client.closed for client in clients)


def test_empty_catalog_removes_unused_destination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        AppConfig,
        "get_temp_directory",
        lambda: tmp_path / "temporary",
    )
    provider = MemoryGroupProvider()
    clients: list[MemorySteamClient] = []

    def client_factory() -> MemorySteamClient:
        client = MemorySteamClient({}, tmp_path / "steam")
        clients.append(client)
        return client

    result = GroupHandoffService.download_latest(
        "project-123",
        provider,
        client_factory=client_factory,
        destination_directory=tmp_path / "packages",
    )

    assert result is None
    assert list((tmp_path / "packages").iterdir()) == []
    assert clients[0].closed is True
