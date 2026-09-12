from pathlib import Path

from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_manifest import SteamGroupManifest
from app.steam.group_manifest_transport import SteamGroupManifestTransport
from app.steam.ugc_client import SteamPublishedItem, SteamUgcVisibility
from tests.steam.test_device_identity import MemoryProtector


class FakeUgcClient:
    def __init__(self, download_directory: Path) -> None:
        self.download_directory = download_directory
        self.published: list[tuple[Path, dict[str, object]]] = []
        self.updated: list[tuple[str, Path, dict[str, object]]] = []

    def publish_item(self, content_directory: Path, **kwargs: object):
        self.published.append((content_directory, kwargs))
        self._capture(content_directory)
        return SteamPublishedItem("3797671909", True)

    def update_item(
        self, published_file_id: str, content_directory: Path, **kwargs: object
    ):
        self.updated.append((published_file_id, content_directory, kwargs))
        self._capture(content_directory)
        return SteamPublishedItem(published_file_id)

    def download_item(self, _published_file_id: str) -> Path:
        return self.download_directory

    def delete_item(self, _published_file_id: str) -> None:
        raise AssertionError("Manifest transport must not delete its stable item.")

    def _capture(self, source: Path) -> None:
        self.download_directory.mkdir(parents=True, exist_ok=True)
        target = self.download_directory / SteamGroupManifestTransport.FILE_NAME
        target.write_bytes(
            (source / SteamGroupManifestTransport.FILE_NAME).read_bytes()
        )


def _manifest(tmp_path: Path) -> SteamGroupManifest:
    administrator = SteamDeviceIdentityStore(
        tmp_path / "identity.json",
        protector=MemoryProtector(),
    ).load_or_create("76561198000000001")
    return SteamGroupManifest.create("Family Worlds", administrator)[0]


def test_manifest_transport_publishes_then_downloads_signed_manifest(
    tmp_path: Path,
) -> None:
    client = FakeUgcClient(tmp_path / "download")
    legal_urls: list[str] = []
    transport = SteamGroupManifestTransport(
        client,
        tmp_path / "temporary",
        legal_urls.append,
    )
    manifest = _manifest(tmp_path)

    item_id = transport.publish(manifest)
    restored = transport.download(item_id)

    assert item_id == "3797671909"
    assert restored == manifest
    assert legal_urls == ["steam://url/CommunityFilePage/3797671909"]
    assert client.published[0][1]["visibility"] == SteamUgcVisibility.UNLISTED
    assert '"kind":"saveshift-group-manifest"' in str(
        client.published[0][1]["metadata"]
    )


def test_manifest_transport_updates_same_item_without_deleting(
    tmp_path: Path,
) -> None:
    client = FakeUgcClient(tmp_path / "download")
    transport = SteamGroupManifestTransport(client, tmp_path / "temporary")
    manifest = _manifest(tmp_path)

    transport.update("3797671909", manifest)

    assert client.updated[0][0] == "3797671909"
    assert transport.download("3797671909") == manifest
