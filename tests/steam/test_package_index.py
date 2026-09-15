from dataclasses import replace
from pathlib import Path

from app.steam.package_index import SteamMemberPackageIndex
from app.steam.session_media import SteamSessionMediaReference
from tests.steam.test_package_descriptor import _identities


def test_member_package_index_round_trips_and_verifies(tmp_path: Path) -> None:
    _administrator, member, manifest, _key = _identities(tmp_path)
    index = SteamMemberPackageIndex.create(
        group_id=manifest.group_id,
        publisher=member,
        workshop_item_id="3797671910",
    ).add("3797671909", member)

    restored = SteamMemberPackageIndex.from_json(index.to_json())

    assert restored == index
    assert restored.package_item_ids == ("3797671909",)
    assert restored.verify(manifest, expected_workshop_item_id="3797671910")


def test_member_package_index_rejects_tampering_and_revocation(tmp_path: Path) -> None:
    administrator, member, manifest, _key = _identities(tmp_path)
    index = SteamMemberPackageIndex.create(
        group_id=manifest.group_id,
        publisher=member,
        workshop_item_id="3797671910",
    )

    assert not replace(index, package_item_ids=("3797671909",)).verify(manifest)
    revoked, _replacement = manifest.revoke_member(member.device_id, administrator)
    assert not index.verify(revoked)


def test_only_index_publisher_can_add_packages(tmp_path: Path) -> None:
    administrator, member, manifest, _key = _identities(tmp_path)
    index = SteamMemberPackageIndex.create(
        group_id=manifest.group_id,
        publisher=member,
        workshop_item_id="3797671910",
    )

    try:
        index.add("3797671909", administrator)
    except ValueError as error:
        assert "publisher" in str(error)
    else:
        raise AssertionError("A different member updated the package index.")


def test_member_package_index_carries_exact_signed_session_media(tmp_path: Path) -> None:
    _administrator, member, manifest, _key = _identities(tmp_path)
    index = SteamMemberPackageIndex.create(
        group_id=manifest.group_id,
        publisher=member,
        workshop_item_id="3797671910",
    )
    reference = SteamSessionMediaReference(
        project_uuid="12345678-1234-4678-9234-567812345678",
        project_version=4,
        package_item_id="3797671909",
        package_checksum="a" * 64,
        media_item_id="3797671911",
        image_checksum="b" * 64,
        key_epoch=1,
        captured_at_utc="2026-09-14T12:00:00+00:00",
    )

    updated = index.add_session_media(reference, member)
    restored = SteamMemberPackageIndex.from_json(updated.to_json())

    assert restored.session_media == (reference,)
    assert restored.verify(manifest)
    assert not replace(
        restored,
        session_media=(replace(reference, image_checksum="c" * 64),),
    ).verify(manifest)

    cleared = restored.remove_session_media(reference.project_uuid, member)
    assert cleared.session_media == ()
    assert cleared.verify(manifest)


def test_schema_one_package_index_still_round_trips(tmp_path: Path) -> None:
    _administrator, member, manifest, _key = _identities(tmp_path)
    current = SteamMemberPackageIndex.create(
        group_id=manifest.group_id,
        publisher=member,
        workshop_item_id="3797671910",
    )
    legacy = replace(current, schema_version=1, signature="")._signed(member)

    restored = SteamMemberPackageIndex.from_json(legacy.to_json())

    assert restored.schema_version == 1
    assert restored.session_media == ()
    assert restored.verify(manifest)
