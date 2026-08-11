import json
from pathlib import Path

import pytest

from app.package_transport.errors import PackageTransportError
from app.package_transport.models import PackageArtifact, PackageDescriptor
from app.steam.constants import (
    SAVESHIFT_STEAM_APP_ID,
    STEAM_UGC_PAYLOAD_NAME,
)
from app.steam.ugc_client import SteamPublishedItem, SteamUgcVisibility
from app.steam.ugc_transport import SteamUgcBlobTransport


class FakeSteamUgcClient:
    def __init__(self, storage_directory: Path) -> None:
        self.storage_directory = storage_directory
        self.publish_calls: list[dict[str, object]] = []
        self.download_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.published_file_id = "987654321"
        self.needs_agreement = False

    def publish_item(
        self,
        content_directory: Path,
        *,
        title: str,
        description: str,
        metadata: str,
        visibility: SteamUgcVisibility,
    ) -> SteamPublishedItem:
        self.storage_directory.mkdir(parents=True, exist_ok=True)
        stored_payload = self.storage_directory / STEAM_UGC_PAYLOAD_NAME
        stored_payload.write_bytes(
            (content_directory / STEAM_UGC_PAYLOAD_NAME).read_bytes()
        )
        self.publish_calls.append(
            {
                "title": title,
                "description": description,
                "metadata": metadata,
                "visibility": visibility,
            }
        )
        return SteamPublishedItem(
            published_file_id=self.published_file_id,
            user_needs_legal_agreement=self.needs_agreement,
        )

    def download_item(self, published_file_id: str) -> Path:
        self.download_calls.append(published_file_id)
        return self.storage_directory

    def delete_item(self, published_file_id: str) -> None:
        self.delete_calls.append(published_file_id)


def _descriptor() -> PackageDescriptor:
    return PackageDescriptor(
        project_uuid="project-123",
        project_version=7,
        package_checksum="a" * 64,
        package_size_bytes=512,
    )


def _artifact(
    remote_id: str = "987654321",
    encryption_key_id: str | None = None,
) -> PackageArtifact:
    descriptor = _descriptor()
    return PackageArtifact(
        transport_name="steam-ugc",
        remote_id=remote_id,
        project_uuid=descriptor.project_uuid,
        project_version=descriptor.project_version,
        package_checksum=descriptor.package_checksum,
        package_size_bytes=descriptor.package_size_bytes,
        encryption_key_id=encryption_key_id,
    )


def test_publish_creates_unlisted_item_with_safe_metadata(tmp_path: Path) -> None:
    client = FakeSteamUgcClient(tmp_path / "steam-item")
    transport = SteamUgcBlobTransport(client, tmp_path / "temporary")
    payload = tmp_path / "encrypted.ssenc"
    payload.write_bytes(b"opaque encrypted bytes")

    artifact = transport.publish_blob(payload, _descriptor())

    assert artifact == _artifact()
    assert client.storage_directory.joinpath(STEAM_UGC_PAYLOAD_NAME).read_bytes() == (
        payload.read_bytes()
    )
    call = client.publish_calls[0]
    assert call["visibility"] is SteamUgcVisibility.UNLISTED
    assert call["description"] == "Encrypted Save Shift group package."
    assert json.loads(str(call["metadata"])) == {
        "schema": 1,
        "app_id": SAVESHIFT_STEAM_APP_ID,
        "project_uuid": "project-123",
        "project_version": 7,
        "package_checksum": "a" * 64,
        "package_size_bytes": 512,
    }
    assert list((tmp_path / "temporary").iterdir()) == []


def test_publish_surfaces_workshop_agreement_and_cleans_temp(tmp_path: Path) -> None:
    client = FakeSteamUgcClient(tmp_path / "steam-item")
    client.needs_agreement = True
    agreement_urls: list[str] = []
    transport = SteamUgcBlobTransport(
        client,
        tmp_path / "temporary",
        agreement_urls.append,
    )
    payload = tmp_path / "encrypted.ssenc"
    payload.write_bytes(b"opaque encrypted bytes")

    transport.publish_blob(payload, _descriptor())

    assert agreement_urls == [
        "steam://url/CommunityFilePage/987654321"
    ]
    assert list((tmp_path / "temporary").iterdir()) == []


def test_download_copies_payload_from_steam_install_directory(
    tmp_path: Path,
) -> None:
    client = FakeSteamUgcClient(tmp_path / "steam-item")
    client.storage_directory.mkdir()
    client.storage_directory.joinpath(STEAM_UGC_PAYLOAD_NAME).write_bytes(
        b"downloaded encrypted bytes"
    )
    transport = SteamUgcBlobTransport(client, tmp_path / "temporary")
    destination = tmp_path / "download" / "payload.ssenc"

    transport.download_blob(_artifact(), destination)

    assert destination.read_bytes() == b"downloaded encrypted bytes"
    assert client.download_calls == ["987654321"]


def test_download_rejects_missing_payload(tmp_path: Path) -> None:
    client = FakeSteamUgcClient(tmp_path / "empty-item")
    client.storage_directory.mkdir()
    transport = SteamUgcBlobTransport(client)

    with pytest.raises(PackageTransportError, match="does not contain"):
        transport.download_blob(_artifact(), tmp_path / "payload.ssenc")


@pytest.mark.parametrize("remote_id", ["", "not-a-number", "0", "-1"])
def test_invalid_workshop_id_is_rejected(
    tmp_path: Path,
    remote_id: str,
) -> None:
    client = FakeSteamUgcClient(tmp_path / "steam-item")
    transport = SteamUgcBlobTransport(client)

    with pytest.raises(PackageTransportError, match="invalid Workshop"):
        transport.delete(_artifact(remote_id))

    assert client.delete_calls == []


def test_delete_delegates_to_steam(tmp_path: Path) -> None:
    client = FakeSteamUgcClient(tmp_path / "steam-item")
    transport = SteamUgcBlobTransport(client)

    transport.delete(_artifact())

    assert client.delete_calls == ["987654321"]
