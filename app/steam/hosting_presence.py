from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import base64
import binascii
import json
from typing import Iterable
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.coordination.models import LockLease
from app.core.logging import logger
from app.steam.device_identity import SteamDeviceIdentity, _decode
from app.steam.group_manifest import SteamGroupManifest
from app.steam.group_security import _canonical_json
from app.steam.social_client import SteamLobby, SteamSocialClient


@dataclass(frozen=True)
class SteamHostPresence:
    protocol: str
    group_id: str
    project_uuid: str
    lease_id: str
    host_steam_id: str
    host_device_id: str
    host_display_name: str
    started_at_utc: str
    signature: str
    lobby_id: str = ""

    PROTOCOL = "saveshift-host-v1"

    @classmethod
    def create(
        cls,
        *,
        group_id: str,
        project_uuid: str,
        host_display_name: str,
        identity: SteamDeviceIdentity,
        started_at: datetime | None = None,
    ) -> "SteamHostPresence":
        name = " ".join(host_display_name.split()).strip()
        if not name or len(name) > 80:
            raise ValueError("A Steam host name must contain 1 to 80 characters.")
        unsigned = {
            "protocol": cls.PROTOCOL,
            "group_id": str(uuid.UUID(group_id)),
            "project_uuid": str(uuid.UUID(project_uuid)),
            "lease_id": str(uuid.uuid4()),
            "host_steam_id": identity.steam_id,
            "host_device_id": identity.device_id,
            "host_display_name": name,
            "started_at_utc": (started_at or datetime.now(UTC))
            .astimezone(UTC)
            .isoformat(),
        }
        return cls(**unsigned, signature=identity.sign(_canonical_json(unsigned)))

    def encode(self) -> str:
        value = asdict(self)
        value.pop("lobby_id")
        raw = _canonical_json(value)
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @classmethod
    def decode(
        cls,
        value: str,
        *,
        lobby_id: str,
        lobby_owner_steam_id: str,
        manifest: SteamGroupManifest,
    ) -> "SteamHostPresence":
        try:
            raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            data = json.loads(raw)
            presence = cls(
                protocol=str(data["protocol"]),
                group_id=str(uuid.UUID(str(data["group_id"]))),
                project_uuid=str(uuid.UUID(str(data["project_uuid"]))),
                lease_id=str(uuid.UUID(str(data["lease_id"]))),
                host_steam_id=str(data["host_steam_id"]),
                host_device_id=str(uuid.UUID(str(data["host_device_id"]))),
                host_display_name=" ".join(
                    str(data["host_display_name"]).split()
                ).strip(),
                started_at_utc=str(data["started_at_utc"]),
                signature=str(data["signature"]),
                lobby_id=str(lobby_id),
            )
            started_at = datetime.fromisoformat(presence.started_at_utc)
            if started_at.tzinfo is None:
                raise ValueError("host timestamp has no timezone")
            if (
                presence.protocol != cls.PROTOCOL
                or presence.group_id != manifest.group_id
                or not presence.host_steam_id.isdigit()
                or int(presence.host_steam_id) < 1
                or not presence.host_display_name
                or len(presence.host_display_name) > 80
                or presence.host_steam_id != str(lobby_owner_steam_id)
            ):
                raise ValueError("host metadata does not match its lobby")
            member = next(
                (
                    item
                    for item in manifest.active_members
                    if item.device_id == presence.host_device_id
                    and item.steam_id == presence.host_steam_id
                ),
                None,
            )
            if member is None:
                raise ValueError("lobby owner is not an active group member")
            unsigned = asdict(presence)
            unsigned.pop("signature")
            unsigned.pop("lobby_id")
            Ed25519PublicKey.from_public_bytes(
                _decode(member.signing_public_key)
            ).verify(_decode(presence.signature), _canonical_json(unsigned))
        except (
            KeyError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            binascii.Error,
            json.JSONDecodeError,
            InvalidSignature,
        ) as error:
            raise ValueError("The Steam hosting presence is invalid.") from error
        return presence

    def to_lease(self, *, visible_seconds: int = 90) -> LockLease:
        started = datetime.fromisoformat(self.started_at_utc).astimezone(UTC)
        now = datetime.now(UTC)
        return LockLease(
            project_uuid=self.project_uuid,
            lease_id=self.lease_id,
            fencing_token=int(started.timestamp() * 1_000_000),
            owner_device_id=self.host_device_id,
            owner_display_name=self.host_display_name,
            acquired_at_utc=started,
            expires_at_utc=now + timedelta(seconds=max(30, visible_seconds)),
        )


class SteamHostingPresenceService:
    """Publishes and verifies advisory per-world Steam hosting lobbies."""

    PROTOCOL_KEY = "ss_protocol"
    GROUP_KEY = "ss_group"
    PRESENCE_KEY = "ss_presence"

    def __init__(self, client: SteamSocialClient) -> None:
        self.client = client

    def create(
        self,
        *,
        manifest: SteamGroupManifest,
        identity: SteamDeviceIdentity,
        project_uuid: str,
        host_display_name: str,
    ) -> tuple[SteamLobby, SteamHostPresence]:
        presence = SteamHostPresence.create(
            group_id=manifest.group_id,
            project_uuid=project_uuid,
            host_display_name=host_display_name,
            identity=identity,
        )
        lobby = self.client.create_searchable_lobby(
            metadata={
                self.PROTOCOL_KEY: SteamHostPresence.PROTOCOL,
                self.GROUP_KEY: manifest.group_id,
            }
        )
        try:
            self.client.set_lobby_data(
                lobby.lobby_id,
                self.PRESENCE_KEY,
                presence.encode(),
            )
        except Exception:
            self.client.leave_lobby(lobby.lobby_id)
            raise
        return lobby, SteamHostPresence(**{**asdict(presence), "lobby_id": lobby.lobby_id})

    def find(
        self,
        manifest: SteamGroupManifest,
        *,
        project_uuids: Iterable[str] | None = None,
    ) -> dict[str, SteamHostPresence]:
        wanted = (
            {str(uuid.UUID(item)) for item in project_uuids}
            if project_uuids is not None
            else None
        )
        lobbies = self.client.find_lobbies(
            {
                self.PROTOCOL_KEY: SteamHostPresence.PROTOCOL,
                self.GROUP_KEY: manifest.group_id,
            }
        )
        candidates: dict[str, list[SteamHostPresence]] = {}
        for lobby in lobbies:
            try:
                owner_steam_id = self.client.lobby_owner(lobby.lobby_id)
                presence = SteamHostPresence.decode(
                    self.client.lobby_data(lobby.lobby_id, self.PRESENCE_KEY),
                    lobby_id=lobby.lobby_id,
                    lobby_owner_steam_id=owner_steam_id,
                    manifest=manifest,
                )
            except Exception as error:
                # Steam can return a lobby-list entry whose owner has already
                # left while we are reading its metadata.  That stale lobby
                # must not make every other world's lock status unavailable.
                logger.warning(
                    "Rejected Steam hosting lobby %s: %s",
                    lobby.lobby_id,
                    error,
                )
                continue
            if wanted is None or presence.project_uuid in wanted:
                candidates.setdefault(presence.project_uuid, []).append(presence)
        found = {
            project_uuid: sorted(
                items,
                key=lambda item: (item.started_at_utc, int(item.lobby_id)),
            )[0]
            for project_uuid, items in candidates.items()
        }
        logger.info(
            "steam.hosting_presence searched=%d accepted=%d projects=%s",
            len(lobbies),
            sum(len(items) for items in candidates.values()),
            ",".join(sorted(found)) or "none",
        )
        return found

    def verify_owned(self, presence: SteamHostPresence) -> None:
        identity = self.client.current_identity()
        if (
            identity.steam_id != presence.host_steam_id
            or self.client.lobby_owner(presence.lobby_id) != presence.host_steam_id
            or self.client.lobby_data(
                presence.lobby_id,
                self.PRESENCE_KEY,
            )
            != presence.encode()
        ):
            raise ValueError("This computer no longer owns its Steam hosting lobby.")

    def release(self, presence: SteamHostPresence) -> None:
        self.client.leave_lobby(presence.lobby_id)
