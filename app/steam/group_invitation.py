from dataclasses import asdict, dataclass
import json
from typing import Protocol
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.steam.device_identity import SteamDeviceIdentity, _decode
from app.steam.group_manifest import SteamGroupManifest
from app.steam.group_security import _canonical_json
from app.steam.social_client import SteamLobby, SteamLobbyMessage, SteamSocialClient


_PROTOCOL = "saveshift-group-invite-v1"


class _ManifestTransport(Protocol):
    def update(self, manifest_item_id: str, manifest: SteamGroupManifest) -> None:
        ...

    def download(self, manifest_item_id: str) -> SteamGroupManifest:
        ...


@dataclass(frozen=True)
class SteamGroupJoinRequest:
    group_id: str
    steam_id: str
    device_id: str
    signing_public_key: str
    agreement_public_key: str
    signature: str

    @classmethod
    def create(
        cls,
        group_id: str,
        identity: SteamDeviceIdentity,
    ) -> "SteamGroupJoinRequest":
        unsigned = {
            "group_id": str(uuid.UUID(group_id)),
            "steam_id": identity.steam_id,
            "device_id": identity.device_id,
            "signing_public_key": identity.signing_public_key,
            "agreement_public_key": identity.agreement_public_key,
        }
        return cls(**unsigned, signature=identity.sign(_canonical_json(unsigned)))

    def verify(self, sender_steam_id: str) -> bool:
        if self.steam_id != sender_steam_id:
            return False
        unsigned = asdict(self)
        signature = unsigned.pop("signature")
        try:
            uuid.UUID(self.group_id)
            uuid.UUID(self.device_id)
            signing_key = _decode(self.signing_public_key)
            if len(signing_key) != 32 or len(_decode(self.agreement_public_key)) != 32:
                return False
            Ed25519PublicKey.from_public_bytes(signing_key).verify(
                _decode(signature),
                _canonical_json(unsigned),
            )
        except (InvalidSignature, TypeError, ValueError):
            return False
        return True

    def to_message(self) -> bytes:
        return _message("join-request", asdict(self))

    @classmethod
    def from_message(cls, payload: bytes) -> "SteamGroupJoinRequest":
        value = _parse_message(payload, "join-request")
        try:
            return cls(**{field: str(value[field]) for field in cls.__annotations__})
        except (KeyError, TypeError) as error:
            raise ValueError("The Steam group join request is invalid.") from error


@dataclass(frozen=True)
class SteamGroupJoinResponse:
    group_id: str
    manifest_item_id: str
    manifest_revision: int
    recipient_device_id: str

    def to_message(self) -> bytes:
        return _message("join-response", asdict(self))

    @classmethod
    def from_message(cls, payload: bytes) -> "SteamGroupJoinResponse":
        value = _parse_message(payload, "join-response")
        try:
            response = cls(
                group_id=str(uuid.UUID(str(value["group_id"]))),
                manifest_item_id=str(value["manifest_item_id"]),
                manifest_revision=int(value["manifest_revision"]),
                recipient_device_id=str(
                    uuid.UUID(str(value["recipient_device_id"]))
                ),
            )
            if (
                not response.manifest_item_id.isdigit()
                or response.manifest_revision < 1
            ):
                raise ValueError("invalid manifest coordinates")
            return response
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("The Steam group join response is invalid.") from error


@dataclass(frozen=True)
class JoinedSteamGroup:
    manifest_item_id: str
    manifest: SteamGroupManifest
    group_key: bytes
    device_id: str
    steam_id: str


class SteamGroupInvitationService:
    """Runs the authenticated device-enrollment ceremony through a Steam lobby."""

    def __init__(
        self,
        social: SteamSocialClient,
        manifests: _ManifestTransport,
    ) -> None:
        self.social = social
        self.manifests = manifests

    def begin_invitation(
        self,
        manifest: SteamGroupManifest,
        manifest_item_id: str,
    ) -> SteamLobby:
        identity = self.social.current_identity()
        if identity.steam_id != manifest.administrator_steam_id:
            raise ValueError("Only the Steam group administrator can invite members.")
        lobby = self.social.create_private_lobby(
            metadata={
                "saveshift_protocol": _PROTOCOL,
                "saveshift_group_id": manifest.group_id,
                "saveshift_manifest_item": manifest_item_id,
            }
        )
        self.social.open_invite_overlay(lobby.lobby_id)
        return lobby

    def request_membership(
        self,
        lobby_id: str,
        identity: SteamDeviceIdentity,
    ) -> SteamGroupJoinRequest:
        if self.social.current_identity().steam_id != identity.steam_id:
            raise ValueError("The device identity does not match the signed-in Steam account.")
        if self.social.lobby_data(lobby_id, "saveshift_protocol") != _PROTOCOL:
            raise ValueError("This is not a Save Shift group invitation lobby.")
        group_id = self.social.lobby_data(lobby_id, "saveshift_group_id")
        request = SteamGroupJoinRequest.create(group_id, identity)
        self.social.send_lobby_message(lobby_id, request.to_message())
        return request

    def admit_member(
        self,
        event: SteamLobbyMessage,
        manifest_item_id: str,
        manifest: SteamGroupManifest,
        group_key: bytes,
        administrator: SteamDeviceIdentity,
    ) -> SteamGroupManifest:
        if self.social.current_identity().steam_id != administrator.steam_id:
            raise ValueError("The administrator identity does not match Steam.")
        request = SteamGroupJoinRequest.from_message(event.payload)
        if request.group_id != manifest.group_id or not request.verify(
            event.sender_steam_id
        ):
            raise ValueError("The Steam group join request could not be authenticated.")
        updated = manifest.add_public_member(
            steam_id=request.steam_id,
            device_id=request.device_id,
            signing_public_key=request.signing_public_key,
            agreement_public_key=request.agreement_public_key,
            group_key=group_key,
            administrator=administrator,
        )
        self.manifests.update(manifest_item_id, updated)
        self.social.send_lobby_message(
            event.lobby_id,
            SteamGroupJoinResponse(
                group_id=updated.group_id,
                manifest_item_id=manifest_item_id,
                manifest_revision=updated.revision,
                recipient_device_id=request.device_id,
            ).to_message(),
        )
        return updated

    def complete_membership(
        self,
        event: SteamLobbyMessage,
        identity: SteamDeviceIdentity,
    ) -> JoinedSteamGroup:
        response = SteamGroupJoinResponse.from_message(event.payload)
        if response.recipient_device_id != identity.device_id:
            raise ValueError("This Steam group response belongs to another device.")
        manifest = self.manifests.download(response.manifest_item_id)
        if manifest.group_id != response.group_id:
            raise ValueError("The downloaded manifest belongs to another group.")
        if manifest.revision < response.manifest_revision:
            raise ValueError("Steam returned an older group manifest revision.")
        owner = self.social.lobby_owner(event.lobby_id)
        if (
            event.sender_steam_id != owner
            or manifest.administrator_steam_id != owner
        ):
            raise ValueError("The invitation was not sent by the group administrator.")
        return JoinedSteamGroup(
            manifest_item_id=response.manifest_item_id,
            manifest=manifest,
            group_key=manifest.group_key_for(identity),
            device_id=identity.device_id,
            steam_id=identity.steam_id,
        )


def _message(kind: str, body: dict[str, object]) -> bytes:
    return _canonical_json(
        {
            "protocol": _PROTOCOL,
            "kind": kind,
            "body": body,
        }
    )


def _parse_message(payload: bytes, expected_kind: str) -> dict[str, object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("The Steam invitation message is invalid.") from error
    if (
        not isinstance(value, dict)
        or value.get("protocol") != _PROTOCOL
        or value.get("kind") != expected_kind
        or not isinstance(value.get("body"), dict)
    ):
        raise ValueError("The Steam invitation message is invalid.")
    return value["body"]
