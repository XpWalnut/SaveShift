import shutil
from pathlib import Path

import pytest

from app.coordination.errors import LockConflictError, PackageCatalogConflictError
from app.coordination.models import PackageCatalogMetadata
from app.package_transport.models import PackageArtifact
from app.steam.constants import STEAM_UGC_PAYLOAD_NAME
from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_manifest import SteamGroupManifest
from app.steam.group_manifest_transport import SteamGroupManifestTransport
from app.steam.native_provider import SteamNativeCoordinationProvider
from app.steam.manifest_cache import SteamGroupManifestCache
from app.steam.package_index_transport import SteamMemberPackageIndexTransport
from app.steam.social_client import SteamIdentity
from app.steam.social_client import SteamLobby
from app.steam.ugc_client import SteamPublishedItem
from tests.steam.test_device_identity import MemoryProtector


class MemoryUgcClient:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir()
        self.next_item_id = 3797671909
        self.next_lobby_id = 109775240917155001
        self.lobbies: dict[str, dict[str, object]] = {}

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

    def create_searchable_lobby(
        self,
        *,
        maximum_members: int = 16,
        metadata=None,
    ) -> SteamLobby:
        lobby = SteamLobby(str(self.next_lobby_id))
        self.next_lobby_id += 1
        self.lobbies[lobby.lobby_id] = {
            "owner": self.current_identity().steam_id,
            "metadata": dict(metadata or {}),
        }
        return lobby

    def find_lobbies(self, metadata, *, maximum_results: int = 50):
        return [
            SteamLobby(lobby_id)
            for lobby_id, value in self.lobbies.items()
            if all(
                value["metadata"].get(key) == expected
                for key, expected in metadata.items()
            )
        ][:maximum_results]

    def set_lobby_data(self, lobby_id: str, key: str, value: str) -> None:
        self.lobbies[lobby_id]["metadata"][key] = value

    def lobby_data(self, lobby_id: str, key: str) -> str:
        return str(self.lobbies[lobby_id]["metadata"].get(key, ""))

    def lobby_owner(self, lobby_id: str) -> str:
        return str(self.lobbies[lobby_id]["owner"])

    def leave_lobby(self, lobby_id: str) -> None:
        self.lobbies.pop(lobby_id, None)

    def poll_social_events(self) -> list[object]:
        return []

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
            manifest_cache=SteamGroupManifestCache(tmp_path / "manifest-cache"),
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


def test_native_hosting_lock_uses_signed_ephemeral_lobby_and_blocks_peer(
    tmp_path: Path,
) -> None:
    client, _manifest, _group_key, create_provider = _provider_setup(tmp_path)
    first = create_provider()
    second = create_provider()
    project_uuid = "12345678-1234-4678-9234-567812345678"

    lease = first.acquire_hosting_lock(project_uuid, "Jake")

    assert len(client.lobbies) == 1
    checkpoint = first.host_session_checkpoint(lease)
    assert checkpoint.project_uuid == project_uuid
    assert checkpoint.parent_descriptor_hash == ""
    assert second.get_lock(project_uuid).owner_display_name == "Jake"
    with pytest.raises(LockConflictError, match="already hosting"):
        second.acquire_hosting_lock(project_uuid, "Hunter")

    first.release_lock(lease)

    assert client.lobbies == {}
    assert second.get_lock(project_uuid) is None


def test_native_provider_close_removes_owned_hosting_presence(
    tmp_path: Path,
) -> None:
    client, _manifest, _group_key, create_provider = _provider_setup(tmp_path)
    provider = create_provider()
    project_uuid = "12345678-1234-4678-9234-567812345678"

    provider.acquire_hosting_lock(project_uuid, "Jake")
    provider.close()

    assert client.lobbies == {}
    assert provider.get_lock(project_uuid) is None


def test_interrupted_host_recovery_refuses_to_rebase_local_work(
    tmp_path: Path,
) -> None:
    client, _manifest, _group_key, create_provider = _provider_setup(tmp_path)
    provider = create_provider()
    project_uuid = "12345678-1234-4678-9234-567812345678"

    with pytest.raises(PackageCatalogConflictError, match="advanced"):
        provider.acquire_recovery_lock(project_uuid, "Jake", "a" * 64)

    assert client.lobbies == {}


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
