from dataclasses import replace
from pathlib import Path

from app.steam.package_index import SteamMemberPackageIndex
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
