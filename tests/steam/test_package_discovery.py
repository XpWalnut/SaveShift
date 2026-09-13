from dataclasses import replace
from pathlib import Path

from app.steam.package_descriptor_transport import SteamPackageDescriptorTransport
from app.steam.package_discovery import SteamGroupPackageDiscovery
from app.steam.package_index import SteamMemberPackageIndex
from app.steam.package_index_transport import SteamMemberPackageIndexTransport
from tests.steam.test_package_descriptor import _descriptor, _identities


class DownloadClient:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.downloads: list[str] = []

    def download_item(self, item_id: str) -> Path:
        self.downloads.append(item_id)
        return self.root / item_id


def _write_item(root: Path, item_id: str, name: str, value: str) -> None:
    directory = root / item_id
    directory.mkdir(parents=True)
    (directory / name).write_text(value, encoding="utf-8")


def _indexed_package(tmp_path: Path):
    _administrator, member, manifest, _key = _identities(tmp_path)
    descriptor = _descriptor(manifest, member)
    index = SteamMemberPackageIndex.create(
        group_id=manifest.group_id,
        publisher=member,
        workshop_item_id="3797671910",
    ).add(descriptor.workshop_item_id, member)
    _write_item(
        tmp_path,
        index.workshop_item_id,
        SteamMemberPackageIndexTransport.FILE_NAME,
        index.to_json(),
    )
    _write_item(
        tmp_path,
        descriptor.workshop_item_id,
        SteamPackageDescriptorTransport.FILE_NAME,
        descriptor.to_json(),
    )
    return member, manifest, index, descriptor


def test_discovery_follows_signed_member_index_and_authenticates_descriptor(
    tmp_path: Path,
) -> None:
    _member, manifest, index, descriptor = _indexed_package(tmp_path)
    client = DownloadClient(tmp_path)

    result = SteamGroupPackageDiscovery(client).discover(manifest)

    assert result.descriptors == (descriptor,)
    assert result.rejected == ()
    assert client.downloads == [index.workshop_item_id, descriptor.workshop_item_id]


def test_discovery_rejects_tampered_index(tmp_path: Path) -> None:
    _member, manifest, index, _descriptor_value = _indexed_package(tmp_path)
    path = tmp_path / index.workshop_item_id / SteamMemberPackageIndexTransport.FILE_NAME
    path.write_text(
        replace(index, package_item_ids=("3797671999",)).to_json(),
        encoding="utf-8",
    )

    result = SteamGroupPackageDiscovery(DownloadClient(tmp_path)).discover(manifest)

    assert result.descriptors == ()
    assert len(result.rejected) == 1
    assert "signature" in result.rejected[0].reason


def test_discovery_rejects_package_signed_by_different_index_member(
    tmp_path: Path,
) -> None:
    administrator, member, manifest, _key = _identities(tmp_path)
    descriptor = _descriptor(manifest, administrator)
    index = SteamMemberPackageIndex.create(
        group_id=manifest.group_id,
        publisher=member,
        workshop_item_id="3797671910",
    ).add(descriptor.workshop_item_id, member)
    _write_item(
        tmp_path,
        index.workshop_item_id,
        SteamMemberPackageIndexTransport.FILE_NAME,
        index.to_json(),
    )
    _write_item(
        tmp_path,
        descriptor.workshop_item_id,
        SteamPackageDescriptorTransport.FILE_NAME,
        descriptor.to_json(),
    )

    result = SteamGroupPackageDiscovery(DownloadClient(tmp_path)).discover(manifest)

    assert result.descriptors == ()
    assert "index publisher" in result.rejected[0].reason


def test_revoked_member_index_is_removed_from_manifest(tmp_path: Path) -> None:
    administrator, member, manifest, _key = _identities(tmp_path)
    revoked, _replacement = manifest.revoke_member(member.device_id, administrator)
    client = DownloadClient(tmp_path)

    SteamGroupPackageDiscovery(client).discover(revoked)

    assert revoked.member_package_indexes == ()
    assert client.downloads == []
