from pathlib import Path

from app.package_transport.models import PackageArtifact
from app.packages.checksum import calculate_sha256
from app.steam.constants import STEAM_UGC_PAYLOAD_NAME
from app.steam.package_descriptor import SteamPackageDescriptor
from app.steam.package_descriptor_transport import SteamPackageDescriptorTransport
from app.steam.ugc_client import SteamPublishedItem, SteamUgcVisibility
from tests.steam.test_package_descriptor import _identities


class DescriptorClient:
    def __init__(self, content: Path) -> None:
        self.content = content
        self.updated_files: dict[str, bytes] = {}
        self.updated_metadata = ""

    def download_item(self, _item_id: str) -> Path:
        return self.content

    def update_item(
        self,
        published_file_id: str,
        content_directory: Path,
        **options,
    ) -> SteamPublishedItem:
        self.updated_files = {
            path.name: path.read_bytes()
            for path in content_directory.iterdir()
            if path.is_file()
        }
        self.updated_metadata = options["metadata"]
        assert options["visibility"] is SteamUgcVisibility.UNLISTED
        return SteamPublishedItem(published_file_id)


def test_attach_preserves_encrypted_payload_and_adds_signed_descriptor(
    tmp_path: Path,
) -> None:
    _administrator, member, manifest, _key = _identities(tmp_path)
    installed = tmp_path / "installed"
    installed.mkdir()
    payload = installed / STEAM_UGC_PAYLOAD_NAME
    payload.write_bytes(b"encrypted package bytes")
    artifact = PackageArtifact(
        transport_name="steam-ugc",
        remote_id="3797671909",
        project_uuid="12345678-1234-4678-9234-567812345678",
        project_version=4,
        package_checksum="b" * 64,
        package_size_bytes=4096,
        encryption_key_id="steam-group-key-1",
    )
    client = DescriptorClient(installed)

    descriptor = SteamPackageDescriptorTransport(
        client,
        tmp_path / "temporary",
    ).attach(
        artifact,
        manifest=manifest,
        publisher=member,
        parent_descriptor_hash=None,
        project_name="Mistwalkers",
        game_id="valheim",
        created_by="Hunter",
    )

    assert descriptor.verify(manifest)
    assert descriptor.encrypted_payload_checksum == calculate_sha256(payload)
    assert client.updated_files[STEAM_UGC_PAYLOAD_NAME] == payload.read_bytes()
    stored = SteamPackageDescriptor.from_json(
        client.updated_files[SteamPackageDescriptorTransport.FILE_NAME]
    )
    assert stored == descriptor
    assert SteamPackageDescriptor.from_json(client.updated_metadata) == descriptor
    assert list((tmp_path / "temporary").iterdir()) == []
