from pathlib import Path

from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.native_group_service import SteamNativeGroupService
from app.steam.social_client import SteamIdentity
from app.steam.ugc_client import SteamPublishedItem
from tests.steam.test_device_identity import MemoryProtector


class FakeSteamClient:
    def __init__(self) -> None:
        self.closed = False
        self.published_content = ""

    def current_identity(self) -> SteamIdentity:
        return SteamIdentity("76561198000000001", "Jake")

    def publish_item(self, content_directory: Path, **_kwargs: object):
        self.published_content = next(content_directory.iterdir()).read_text(
            encoding="utf-8"
        )
        return SteamPublishedItem("3797671909")

    def close(self) -> None:
        self.closed = True


def test_create_group_binds_manifest_to_signed_in_steam_account(
    tmp_path: Path,
) -> None:
    client = FakeSteamClient()
    service = SteamNativeGroupService(
        client_factory=lambda: client,
        identity_store=SteamDeviceIdentityStore(
            tmp_path / "identity.json", protector=MemoryProtector()
        ),
        temporary_directory=tmp_path / "manifest-upload",
    )

    created = service.create_group("Family Worlds")

    assert created.manifest.name == "Family Worlds"
    assert created.manifest.administrator_steam_id == "76561198000000001"
    assert created.manifest_item_id == "3797671909"
    assert created.identity.device_id == created.manifest.administrator_device_id
    assert '"signature"' in client.published_content
    assert client.closed
