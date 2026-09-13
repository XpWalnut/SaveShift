from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_manifest import SteamGroupManifest
from app.steam.package_descriptor import SteamPackageDescriptor
from tests.steam.test_device_identity import MemoryProtector


def _identities(tmp_path: Path):
    administrator = SteamDeviceIdentityStore(
        tmp_path / "administrator.json", protector=MemoryProtector()
    ).load_or_create("76561198000000001")
    member = SteamDeviceIdentityStore(
        tmp_path / "member.json", protector=MemoryProtector()
    ).load_or_create("76561198000000002")
    manifest, key = SteamGroupManifest.create("Friends", administrator)
    return (
        administrator,
        member,
        manifest.add_member(
            member,
            key,
            administrator,
            package_index_item_id="3797671910",
        ),
        key,
    )


def _descriptor(manifest, publisher, **changes) -> SteamPackageDescriptor:
    values = {
        "manifest": manifest,
        "publisher": publisher,
        "project_uuid": "12345678-1234-4678-9234-567812345678",
        "project_version": 3,
        "parent_descriptor_hash": None,
        "encrypted_payload_checksum": "a" * 64,
        "package_checksum": "b" * 64,
        "package_size_bytes": 2048,
        "workshop_item_id": "3797671909",
        "project_name": "Mistwalkers",
        "game_id": "valheim",
        "created_by": "Hunter",
        "published_at": datetime(2026, 9, 12, tzinfo=UTC),
        "version_id": "aaaaaaaa-1234-4678-9234-567812345678",
    }
    values.update(changes)
    return SteamPackageDescriptor.create(**values)


def test_signed_descriptor_round_trips_through_workshop_metadata(tmp_path: Path) -> None:
    _administrator, member, manifest, _key = _identities(tmp_path)
    descriptor = _descriptor(manifest, member)

    restored = SteamPackageDescriptor.from_json(descriptor.to_json(compact=True))

    assert restored == descriptor
    assert restored.verify(manifest, expected_workshop_item_id="3797671909")
    assert len(restored.descriptor_hash) == 64


def test_descriptor_rejects_tampering_and_wrong_workshop_item(tmp_path: Path) -> None:
    _administrator, member, manifest, _key = _identities(tmp_path)
    descriptor = _descriptor(manifest, member)

    assert not replace(descriptor, project_version=99).verify(manifest)
    assert not descriptor.verify(manifest, expected_workshop_item_id="3797671910")


def test_descriptor_from_revoked_device_is_no_longer_accepted(tmp_path: Path) -> None:
    administrator, member, manifest, _key = _identities(tmp_path)
    descriptor = _descriptor(manifest, member)
    revoked, _replacement_key = manifest.revoke_member(
        member.device_id,
        administrator,
    )

    assert descriptor.verify(manifest)
    assert not descriptor.verify(revoked)
