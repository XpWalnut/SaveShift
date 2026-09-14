from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_manifest import SteamGroupManifest
from app.steam.hosting_presence import (
    SteamHostPresence,
    SteamHostingPresenceService,
)
from app.steam.social_client import SteamIdentity, SteamLobby
from tests.steam.test_device_identity import MemoryProtector


class MemorySocialClient:
    def __init__(self, steam_id: str) -> None:
        self.steam_id = steam_id
        self.next_lobby_id = 100
        self.lobbies: dict[str, dict[str, object]] = {}

    def current_identity(self) -> SteamIdentity:
        return SteamIdentity(self.steam_id, "Host")

    def create_searchable_lobby(
        self,
        *,
        maximum_members: int = 16,
        metadata=None,
    ) -> SteamLobby:
        lobby = SteamLobby(str(self.next_lobby_id))
        self.next_lobby_id += 1
        self.lobbies[lobby.lobby_id] = {
            "owner": self.steam_id,
            "metadata": dict(metadata or {}),
        }
        return lobby

    def set_lobby_data(self, lobby_id: str, key: str, value: str) -> None:
        self.lobbies[lobby_id]["metadata"][key] = value

    def lobby_data(self, lobby_id: str, key: str) -> str:
        return str(self.lobbies[lobby_id]["metadata"].get(key, ""))

    def lobby_owner(self, lobby_id: str) -> str:
        return str(self.lobbies[lobby_id]["owner"])

    def find_lobbies(self, metadata, *, maximum_results: int = 50):
        return [
            SteamLobby(lobby_id)
            for lobby_id, value in self.lobbies.items()
            if all(value["metadata"].get(key) == expected for key, expected in metadata.items())
        ][:maximum_results]

    def leave_lobby(self, lobby_id: str) -> None:
        self.lobbies.pop(lobby_id, None)


def _group(tmp_path: Path):
    identity = SteamDeviceIdentityStore(
        tmp_path / "identity.json",
        protector=MemoryProtector(),
    ).load_or_create("76561198000000001")
    manifest, _group_key = SteamGroupManifest.create("Family Worlds", identity)
    return identity, manifest


def test_hosting_presence_is_signed_discoverable_and_ephemeral(tmp_path: Path) -> None:
    identity, manifest = _group(tmp_path)
    client = MemorySocialClient(identity.steam_id)
    service = SteamHostingPresenceService(client)
    project_uuid = "12345678-1234-4678-9234-567812345678"

    lobby, created = service.create(
        manifest=manifest,
        identity=identity,
        project_uuid=project_uuid,
        host_display_name="  Jake  ",
    )
    found = service.find(manifest, project_uuids=[project_uuid])

    assert found[project_uuid] == created
    assert found[project_uuid].host_display_name == "Jake"
    assert found[project_uuid].to_lease().owner_device_id == identity.device_id
    service.verify_owned(created)

    service.release(created)

    assert lobby.lobby_id not in client.lobbies
    assert service.find(manifest, project_uuids=[project_uuid]) == {}


def test_hosting_presence_rejects_tampered_or_spoofed_lobby(tmp_path: Path) -> None:
    identity, manifest = _group(tmp_path)
    client = MemorySocialClient(identity.steam_id)
    service = SteamHostingPresenceService(client)
    project_uuid = "12345678-1234-4678-9234-567812345678"
    _lobby, created = service.create(
        manifest=manifest,
        identity=identity,
        project_uuid=project_uuid,
        host_display_name="Jake",
    )

    client.lobbies[created.lobby_id]["owner"] = "76561198000000002"
    assert service.find(manifest, project_uuids=[project_uuid]) == {}

    client.lobbies[created.lobby_id]["owner"] = identity.steam_id
    encoded = client.lobby_data(created.lobby_id, service.PRESENCE_KEY)
    client.set_lobby_data(created.lobby_id, service.PRESENCE_KEY, encoded[:-1] + "A")
    assert service.find(manifest, project_uuids=[project_uuid]) == {}


def test_duplicate_hosting_lobbies_choose_the_earliest_signed_presence(
    tmp_path: Path,
) -> None:
    identity, manifest = _group(tmp_path)
    client = MemorySocialClient(identity.steam_id)
    service = SteamHostingPresenceService(client)
    project_uuid = "12345678-1234-4678-9234-567812345678"
    earlier = SteamHostPresence.create(
        group_id=manifest.group_id,
        project_uuid=project_uuid,
        host_display_name="Earlier",
        identity=identity,
        started_at=datetime.now(UTC) - timedelta(seconds=5),
    )
    later = SteamHostPresence.create(
        group_id=manifest.group_id,
        project_uuid=project_uuid,
        host_display_name="Later",
        identity=identity,
    )
    for presence in (later, earlier):
        lobby = client.create_searchable_lobby(
            metadata={
                service.PROTOCOL_KEY: SteamHostPresence.PROTOCOL,
                service.GROUP_KEY: manifest.group_id,
            }
        )
        client.set_lobby_data(lobby.lobby_id, service.PRESENCE_KEY, presence.encode())

    assert service.find(manifest)[project_uuid].host_display_name == "Earlier"
