from pathlib import Path

import pytest

from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_invitation import SteamGroupInvitationService
from app.steam.group_manifest import SteamGroupManifest
from app.steam.social_client import SteamIdentity, SteamLobby, SteamLobbyMessage
from tests.steam.test_device_identity import MemoryProtector


class SharedLobby:
    lobby_id = "109775240917155001"

    def __init__(self, owner_steam_id: str) -> None:
        self.owner_steam_id = owner_steam_id
        self.metadata: dict[str, str] = {}
        self.messages: list[tuple[str, bytes]] = []
        self.overlay_opened = False


class FakeSocialClient:
    def __init__(self, steam_id: str, lobby: SharedLobby) -> None:
        self.steam_id = steam_id
        self.lobby = lobby

    def current_identity(self) -> SteamIdentity:
        return SteamIdentity(self.steam_id, f"User {self.steam_id[-2:]}")

    def create_private_lobby(self, *, maximum_members=16, metadata=None):
        assert maximum_members == 16
        self.lobby.metadata.update(metadata or {})
        return SteamLobby(self.lobby.lobby_id)

    def open_invite_overlay(self, lobby_id: str) -> None:
        assert lobby_id == self.lobby.lobby_id
        self.lobby.overlay_opened = True

    def lobby_data(self, lobby_id: str, key: str) -> str:
        assert lobby_id == self.lobby.lobby_id
        return self.lobby.metadata.get(key, "")

    def send_lobby_message(self, lobby_id: str, payload: bytes) -> None:
        assert lobby_id == self.lobby.lobby_id
        self.lobby.messages.append((self.steam_id, payload))

    def lobby_owner(self, lobby_id: str) -> str:
        assert lobby_id == self.lobby.lobby_id
        return self.lobby.owner_steam_id


class MemoryManifestTransport:
    def __init__(self, manifest: SteamGroupManifest) -> None:
        self.manifest = manifest
        self.updated_item_id = ""

    def update(self, manifest_item_id: str, manifest: SteamGroupManifest) -> None:
        self.updated_item_id = manifest_item_id
        self.manifest = manifest

    def download(self, manifest_item_id: str) -> SteamGroupManifest:
        assert manifest_item_id == "3797671909"
        return SteamGroupManifest.from_json(self.manifest.to_json())


def _identity(tmp_path: Path, name: str, steam_id: str):
    return SteamDeviceIdentityStore(
        tmp_path / f"{name}.json", protector=MemoryProtector()
    ).load_or_create(steam_id)


def test_lobby_invitation_enrolls_authenticated_steam_device(tmp_path: Path) -> None:
    administrator = _identity(tmp_path, "administrator", "76561198000000001")
    member = _identity(tmp_path, "member", "76561198000000002")
    manifest, group_key = SteamGroupManifest.create("Friends", administrator)
    lobby = SharedLobby(administrator.steam_id)
    transport = MemoryManifestTransport(manifest)
    administrator_service = SteamGroupInvitationService(
        FakeSocialClient(administrator.steam_id, lobby), transport
    )
    member_service = SteamGroupInvitationService(
        FakeSocialClient(member.steam_id, lobby), transport
    )

    created_lobby = administrator_service.begin_invitation(
        manifest, "3797671909"
    )
    member_service.request_membership(created_lobby.lobby_id, member)
    request_sender, request_payload = lobby.messages[-1]
    updated = administrator_service.admit_member(
        SteamLobbyMessage(created_lobby.lobby_id, request_sender, request_payload),
        "3797671909",
        manifest,
        group_key,
        administrator,
    )
    response_sender, response_payload = lobby.messages[-1]
    joined = member_service.complete_membership(
        SteamLobbyMessage(created_lobby.lobby_id, response_sender, response_payload),
        member,
    )

    assert lobby.overlay_opened
    assert transport.updated_item_id == "3797671909"
    assert joined.manifest == updated
    assert joined.group_key == group_key
    assert any(item.device_id == member.device_id for item in updated.active_members)


def test_join_request_rejects_spoofed_steam_sender(tmp_path: Path) -> None:
    administrator = _identity(tmp_path, "administrator", "76561198000000001")
    member = _identity(tmp_path, "member", "76561198000000002")
    manifest, group_key = SteamGroupManifest.create("Friends", administrator)
    lobby = SharedLobby(administrator.steam_id)
    transport = MemoryManifestTransport(manifest)
    member_service = SteamGroupInvitationService(
        FakeSocialClient(member.steam_id, lobby), transport
    )
    administrator_service = SteamGroupInvitationService(
        FakeSocialClient(administrator.steam_id, lobby), transport
    )
    administrator_service.begin_invitation(manifest, "3797671909")
    member_service.request_membership(lobby.lobby_id, member)
    _, payload = lobby.messages[-1]

    with pytest.raises(ValueError, match="could not be authenticated"):
        administrator_service.admit_member(
            SteamLobbyMessage(lobby.lobby_id, "76561198000000003", payload),
            "3797671909",
            manifest,
            group_key,
            administrator,
        )


def test_join_response_requires_original_lobby_owner(tmp_path: Path) -> None:
    administrator = _identity(tmp_path, "administrator", "76561198000000001")
    member = _identity(tmp_path, "member", "76561198000000002")
    manifest, group_key = SteamGroupManifest.create("Friends", administrator)
    lobby = SharedLobby(administrator.steam_id)
    transport = MemoryManifestTransport(manifest)
    administrator_service = SteamGroupInvitationService(
        FakeSocialClient(administrator.steam_id, lobby), transport
    )
    member_service = SteamGroupInvitationService(
        FakeSocialClient(member.steam_id, lobby), transport
    )
    administrator_service.begin_invitation(manifest, "3797671909")
    member_service.request_membership(lobby.lobby_id, member)
    sender, payload = lobby.messages[-1]
    administrator_service.admit_member(
        SteamLobbyMessage(lobby.lobby_id, sender, payload),
        "3797671909",
        manifest,
        group_key,
        administrator,
    )
    response_sender, response = lobby.messages[-1]
    lobby.owner_steam_id = "76561198000000003"

    with pytest.raises(ValueError, match="group administrator"):
        member_service.complete_membership(
            SteamLobbyMessage(lobby.lobby_id, response_sender, response), member
        )
