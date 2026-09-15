from pathlib import Path

from app.steam.package_index import SteamMemberPackageIndex
from app.steam.package_index_transport import SteamMemberPackageIndexTransport
from app.steam.ugc_client import SteamPublishedItem, SteamUgcVisibility
from tests.steam.test_package_descriptor import _identities


class IndexClient:
    def __init__(self) -> None:
        self.contents: dict[str, dict[str, bytes]] = {}
        self.publish_calls = 0
        self.update_calls = 0

    def publish_item(self, content_directory: Path, **options) -> SteamPublishedItem:
        self.publish_calls += 1
        assert options["visibility"] is SteamUgcVisibility.UNLISTED
        return SteamPublishedItem("3797671910")

    def update_item(
        self,
        published_file_id: str,
        content_directory: Path,
        **options,
    ) -> SteamPublishedItem:
        self.update_calls += 1
        assert options["visibility"] is SteamUgcVisibility.UNLISTED
        self.contents[published_file_id] = {
            path.name: path.read_bytes()
            for path in content_directory.iterdir()
            if path.is_file()
        }
        return SteamPublishedItem(published_file_id)


def test_transport_bootstraps_then_stores_signed_index(tmp_path: Path) -> None:
    _administrator, member, manifest, _key = _identities(tmp_path)
    client = IndexClient()
    transport = SteamMemberPackageIndexTransport(client, tmp_path / "temporary")

    index = transport.publish(group_id=manifest.group_id, publisher=member)

    stored = SteamMemberPackageIndex.from_json(
        client.contents[index.workshop_item_id][transport.FILE_NAME]
    )
    assert stored == index
    assert index.verify(manifest)
    assert client.publish_calls == 1
    assert client.update_calls == 1
    assert list((tmp_path / "temporary").iterdir()) == []
