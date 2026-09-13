import shutil
from pathlib import Path

import pytest

from app.coordination.errors import PackageCatalogConflictError
from app.coordination.models import PackageCatalogMetadata
from app.package_transport.models import PackageArtifact
from app.steam.constants import STEAM_UGC_PAYLOAD_NAME
from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_manifest import SteamGroupManifest
from app.steam.group_manifest_transport import SteamGroupManifestTransport
from app.steam.native_provider import SteamNativeCoordinationProvider
from app.steam.package_index_transport import SteamMemberPackageIndexTransport
from app.steam.social_client import SteamIdentity
from app.steam.ugc_client import SteamPublishedItem
from tests.steam.test_device_identity import MemoryProtector


class MemoryUgcClient:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir()
        self.next_item_id = 3797671909

    def current_identity(self) -> SteamIdentity:
        return SteamIdentity("76561198000000001", "Jake")

    def publish_item(
        self,
        content_directory: Path,
        **_options: object,
    ) -> SteamPublishedItem:
        item_id = str(self.next_item_id)
        self.next_item_id += 1
        shutil.copytree(content_directory, self.root / item_id)
        return SteamPublishedItem(item_id)

    def update_item(
        self,
        published_file_id: str,
        content_directory: Path,
        **_options: object,
    ) -> SteamPublishedItem:
        destination = self.root / published_file_id
        shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(content_directory, destination)
        return SteamPublishedItem(published_file_id)

    def download_item(self, published_file_id: str) -> Path:
        return self.root / published_file_id

    def delete_item(self, published_file_id: str) -> None:
        shutil.rmtree(self.root / published_file_id, ignore_errors=True)

    def close(self) -> None:
        pass


def _provider_setup(tmp_path: Path):
    client = MemoryUgcClient(tmp_path / "ugc")
    identity_store = SteamDeviceIdentityStore(
        tmp_path / "identity.json",
        protector=MemoryProtector(),
    )
    identity = identity_store.load_or_create("76561198000000001")
    manifest, group_key = SteamGroupManifest.create("Family Worlds", identity)
    index = SteamMemberPackageIndexTransport(
        client,
        tmp_path / "index-temp",
    ).publish(group_id=manifest.group_id, publisher=identity)
    manifest = manifest.set_member_package_index(
        device_id=identity.device_id,
        workshop_item_id=index.workshop_item_id,
        administrator=identity,
    )
    manifest_item_id = SteamGroupManifestTransport(
        client,
        tmp_path / "manifest-temp",
    ).publish(manifest)

    def create_provider() -> SteamNativeCoordinationProvider:
        return SteamNativeCoordinationProvider(
            group_id=manifest.group_id,
            manifest_item_id=manifest_item_id,
            package_index_item_id=index.workshop_item_id,
            device_id=identity.device_id,
            client_factory=lambda: client,
            identity_store=identity_store,
        )

    return client, manifest, group_key, create_provider


def _artifact(
    tmp_path: Path,
    client: MemoryUgcClient,
    provider: SteamNativeCoordinationProvider,
    project_uuid: str,
    version: int,
) -> PackageArtifact:
    content = tmp_path / f"payload-{version}-{client.next_item_id}"
    content.mkdir()
    (content / STEAM_UGC_PAYLOAD_NAME).write_bytes(
        f"encrypted package {version}".encode()
    )
    item = client.publish_item(content)
    key = provider.get_package_encryption_key()
    return PackageArtifact(
        transport_name="steam-ugc",
        remote_id=item.published_file_id,
        project_uuid=project_uuid,
        project_version=version,
        package_checksum=f"{version:x}" * 64,
        package_size_bytes=4096,
        encryption_key_id=key.key_id,
    )


def test_native_provider_registers_and_discovers_ancestry_head(
    tmp_path: Path,
) -> None:
    client, _manifest, group_key, create_provider = _provider_setup(tmp_path)
    provider = create_provider()
    project_uuid = "12345678-1234-4678-9234-567812345678"
    lease = provider.acquire_lock(project_uuid, "Jake")
    artifact = _artifact(tmp_path, client, provider, project_uuid, 1)

    registered = provider.register_package(
        artifact,
        lease,
        PackageCatalogMetadata("Mistwalkers", "valheim", "Jake"),
    )

    assert registered.artifact == artifact
    assert provider.latest_package(project_uuid) == registered
    assert provider.list_latest_packages() == [registered]
    assert provider.get_package_encryption_key().key_material == group_key
    provider.release_lock(lease)
    assert provider.get_lock(project_uuid) is None


def test_native_provider_rejects_publish_when_starting_head_advanced(
    tmp_path: Path,
) -> None:
    client, _manifest, _group_key, create_provider = _provider_setup(tmp_path)
    first = create_provider()
    second = create_provider()
    project_uuid = "12345678-1234-4678-9234-567812345678"
    first_lease = first.acquire_lock(project_uuid, "Jake")
    second_lease = second.acquire_lock(project_uuid, "Jake")

    second.register_package(
        _artifact(tmp_path, client, second, project_uuid, 1),
        second_lease,
        PackageCatalogMetadata("Mistwalkers", "valheim", "Jake"),
    )

    with pytest.raises(PackageCatalogConflictError, match="Another group member"):
        first.register_package(
            _artifact(tmp_path, client, first, project_uuid, 1),
            first_lease,
            PackageCatalogMetadata("Mistwalkers", "valheim", "Jake"),
        )
