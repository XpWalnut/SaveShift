from dataclasses import replace
from pathlib import Path

import pytest

from app.database.models.project import Project
from app.package_transport.errors import (
    PackageTransferIntegrityError,
    PackageTransportMismatchError,
)
from app.package_transport.models import PackageArtifact, PackageDescriptor
from app.package_transport.service import PackageTransferService
from app.packages.checksum import calculate_sha256
from app.packages.package_service import PackageService


PROJECT_UUID = "12345678-1234-5678-1234-567812345678"


class MemoryTransport:
    name = "memory"

    def __init__(self) -> None:
        self.payloads: dict[str, bytes] = {}
        self.published_descriptor: PackageDescriptor | None = None
        self.download_calls = 0
        self.delete_calls = 0
        self.artifact_transform = lambda artifact: artifact

    def publish(
        self,
        package_path: Path,
        descriptor: PackageDescriptor,
    ) -> PackageArtifact:
        remote_id = "artifact-1"
        self.payloads[remote_id] = package_path.read_bytes()
        self.published_descriptor = descriptor
        return self.artifact_transform(
            PackageArtifact(
                transport_name=self.name,
                remote_id=remote_id,
                project_uuid=descriptor.project_uuid,
                project_version=descriptor.project_version,
                package_checksum=descriptor.package_checksum,
                package_size_bytes=descriptor.package_size_bytes,
            )
        )

    def download(
        self,
        artifact: PackageArtifact,
        destination_path: Path,
    ) -> None:
        self.download_calls += 1
        destination_path.write_bytes(self.payloads[artifact.remote_id])

    def delete(self, artifact: PackageArtifact) -> None:
        self.delete_calls += 1
        self.payloads.pop(artifact.remote_id, None)


def _create_package(tmp_path: Path, *, version: int = 3) -> Path:
    source_root = tmp_path / "source"
    source_root.mkdir(parents=True)
    save_file = source_root / "world.sav"
    save_file.write_bytes(b"shared-world-state")
    package_path = tmp_path / "source.sspkg"

    PackageService.create_package(
        game_id="abiotic_factor",
        project=Project(
            installed_game_id=1,
            name="Shared World",
            local_path=str(source_root),
            uuid=PROJECT_UUID,
        ),
        project_version=version,
        root_path=source_root,
        save_files=[save_file],
        output_path=package_path,
        created_by="Alice",
    )
    return package_path


def test_publish_sends_verified_immutable_package_descriptor(
    tmp_path: Path,
) -> None:
    package_path = _create_package(tmp_path)
    transport = MemoryTransport()

    artifact = PackageTransferService.publish(package_path, transport)

    assert transport.published_descriptor == PackageDescriptor(
        project_uuid=PROJECT_UUID,
        project_version=3,
        package_checksum=calculate_sha256(package_path),
        package_size_bytes=package_path.stat().st_size,
    )
    assert artifact.transport_name == "memory"
    assert artifact.remote_id == "artifact-1"
    assert transport.payloads[artifact.remote_id] == package_path.read_bytes()


@pytest.mark.parametrize(
    "transform",
    [
        lambda artifact: replace(artifact, remote_id=""),
        lambda artifact: replace(artifact, transport_name="other"),
        lambda artifact: replace(artifact, project_version=999),
        lambda artifact: replace(artifact, package_checksum="0" * 64),
    ],
)
def test_publish_rejects_invalid_provider_response(
    tmp_path: Path,
    transform,
) -> None:
    transport = MemoryTransport()
    transport.artifact_transform = transform

    with pytest.raises(PackageTransferIntegrityError):
        PackageTransferService.publish(_create_package(tmp_path), transport)


def test_download_verifies_package_before_atomically_replacing_destination(
    tmp_path: Path,
) -> None:
    source_path = _create_package(tmp_path)
    transport = MemoryTransport()
    artifact = PackageTransferService.publish(source_path, transport)
    destination = tmp_path / "downloads" / "received.sspkg"
    destination.parent.mkdir()
    destination.write_bytes(b"previous-file")

    result = PackageTransferService.download(
        artifact,
        destination,
        transport,
    )

    assert result == destination
    assert destination.read_bytes() == source_path.read_bytes()
    assert not list(destination.parent.glob("*.part"))


def test_download_failure_preserves_existing_destination_and_removes_partial(
    tmp_path: Path,
) -> None:
    source_path = _create_package(tmp_path)
    transport = MemoryTransport()
    artifact = PackageTransferService.publish(source_path, transport)
    transport.payloads[artifact.remote_id] = b"corrupt"
    destination = tmp_path / "received.sspkg"
    destination.write_bytes(b"keep-me")

    with pytest.raises(PackageTransferIntegrityError):
        PackageTransferService.download(artifact, destination, transport)

    assert destination.read_bytes() == b"keep-me"
    assert not list(tmp_path.glob("*.part"))


def test_wrong_transport_is_rejected_before_download_or_delete(
    tmp_path: Path,
) -> None:
    source_path = _create_package(tmp_path)
    transport = MemoryTransport()
    artifact = PackageTransferService.publish(source_path, transport)
    wrong_transport = MemoryTransport()
    wrong_transport.name = "steam"

    with pytest.raises(PackageTransportMismatchError):
        PackageTransferService.download(
            artifact,
            tmp_path / "received.sspkg",
            wrong_transport,
        )

    with pytest.raises(PackageTransportMismatchError):
        PackageTransferService.delete(artifact, wrong_transport)

    assert wrong_transport.download_calls == 0
    assert wrong_transport.delete_calls == 0


def test_delete_delegates_to_matching_transport(tmp_path: Path) -> None:
    transport = MemoryTransport()
    artifact = PackageTransferService.publish(
        _create_package(tmp_path),
        transport,
    )

    PackageTransferService.delete(artifact, transport)

    assert transport.delete_calls == 1
    assert artifact.remote_id not in transport.payloads
