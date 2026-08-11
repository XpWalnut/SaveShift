from pathlib import Path

import pytest

from app.coordination.models import PackageEncryptionKey
from app.package_transport.encrypted_transport import EncryptedPackageTransport
from app.package_transport.errors import PackageEncryptionError
from app.package_transport.models import PackageArtifact, PackageDescriptor
from app.package_transport.service import PackageTransferService
from tests.package_transport.test_transfer_service import _create_package


class StaticKeyProvider:
    def __init__(self, key: bytes, key_id: str = "key-1") -> None:
        self.key = key
        self.key_id = key_id
        self.calls = 0

    def get_package_encryption_key(
        self,
        key_id: str | None = None,
    ) -> PackageEncryptionKey:
        self.calls += 1
        assert key_id is None or key_id == self.key_id
        return PackageEncryptionKey(
            key_id=self.key_id,
            algorithm="AES-256-GCM",
            key_material=self.key,
        )


class MemoryBlobTransport:
    name = "steam-ugc"

    def __init__(self) -> None:
        self.payloads: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def publish_blob(
        self,
        payload_path: Path,
        descriptor: PackageDescriptor,
    ) -> PackageArtifact:
        remote_id = "ugc-123"
        self.payloads[remote_id] = payload_path.read_bytes()
        return PackageArtifact(
            transport_name=self.name,
            remote_id=remote_id,
            project_uuid=descriptor.project_uuid,
            project_version=descriptor.project_version,
            package_checksum=descriptor.package_checksum,
            package_size_bytes=descriptor.package_size_bytes,
        )

    def download_blob(
        self,
        artifact: PackageArtifact,
        destination_path: Path,
    ) -> None:
        destination_path.write_bytes(self.payloads[artifact.remote_id])

    def delete(self, artifact: PackageArtifact) -> None:
        self.deleted.append(artifact.remote_id)
        self.payloads.pop(artifact.remote_id, None)


def test_encrypted_transport_hides_package_bytes_and_round_trips(
    tmp_path: Path,
) -> None:
    source = _create_package(tmp_path)
    blobs = MemoryBlobTransport()
    keys = StaticKeyProvider(bytes(range(32)))
    transport = EncryptedPackageTransport(blobs, keys, tmp_path / "temporary")

    artifact = PackageTransferService.publish(source, transport)

    assert blobs.payloads[artifact.remote_id] != source.read_bytes()
    assert artifact.encryption_key_id == "key-1"
    destination = PackageTransferService.download(
        artifact,
        tmp_path / "received.sspkg",
        transport,
    )
    assert destination.read_bytes() == source.read_bytes()
    assert keys.calls == 2
    assert list((tmp_path / "temporary").iterdir()) == []


def test_encrypted_transport_rejects_key_from_another_group(
    tmp_path: Path,
) -> None:
    source = _create_package(tmp_path)
    blobs = MemoryBlobTransport()
    original = EncryptedPackageTransport(
        blobs,
        StaticKeyProvider(b"a" * 32),
        tmp_path / "publisher-temp",
    )
    artifact = PackageTransferService.publish(source, original)
    other_group = EncryptedPackageTransport(
        blobs,
        StaticKeyProvider(b"b" * 32),
        tmp_path / "receiver-temp",
    )

    with pytest.raises(PackageEncryptionError, match="authenticated"):
        PackageTransferService.download(
            artifact,
            tmp_path / "received.sspkg",
            other_group,
        )

    assert not (tmp_path / "received.sspkg").exists()
    assert list((tmp_path / "receiver-temp").iterdir()) == []


def test_encrypted_transport_delegates_remote_deletion(tmp_path: Path) -> None:
    blobs = MemoryBlobTransport()
    transport = EncryptedPackageTransport(
        blobs,
        StaticKeyProvider(b"a" * 32),
        tmp_path / "temporary",
    )
    artifact = PackageTransferService.publish(_create_package(tmp_path), transport)

    PackageTransferService.delete(artifact, transport)

    assert blobs.deleted == [artifact.remote_id]
    assert blobs.payloads == {}
