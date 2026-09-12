from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.steam.device_identity import (
    SteamDeviceIdentity,
    SteamDeviceIdentityStore,
)
from app.steam.group_manifest import SteamGroupManifest
from app.steam.group_manifest_transport import SteamGroupManifestTransport
from app.steam.native_ugc_client import SteamworksUgcClient
from app.steam.ugc_client import SteamUgcClient


@dataclass(frozen=True)
class CreatedSteamGroup:
    manifest: SteamGroupManifest
    manifest_item_id: str
    identity: SteamDeviceIdentity


class SteamNativeGroupService:
    """Creates the durable local and Workshop state for a Steam-native group."""

    def __init__(
        self,
        *,
        client_factory: Callable[[], SteamUgcClient] = SteamworksUgcClient,
        identity_store: SteamDeviceIdentityStore | None = None,
        temporary_directory: Path | None = None,
        legal_agreement_handler: Callable[[str], None] | None = None,
    ) -> None:
        self.client_factory = client_factory
        self.identity_store = identity_store or SteamDeviceIdentityStore()
        self.temporary_directory = temporary_directory
        self.legal_agreement_handler = legal_agreement_handler

    def create_group(self, name: str) -> CreatedSteamGroup:
        client = self.client_factory()
        try:
            steam_identity = client.current_identity()
            identity = self.identity_store.load_or_create(steam_identity.steam_id)
            manifest, _group_key = SteamGroupManifest.create(name, identity)
            transport = SteamGroupManifestTransport(
                client,
                self.temporary_directory,
                self.legal_agreement_handler,
            )
            manifest_item_id = transport.publish(manifest)
            return CreatedSteamGroup(
                manifest=manifest,
                manifest_item_id=manifest_item_id,
                identity=identity,
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
