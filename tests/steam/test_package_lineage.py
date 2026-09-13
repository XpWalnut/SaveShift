from pathlib import Path

import pytest

from app.steam.package_lineage import SteamPackageForkError, SteamPackageLineage
from tests.steam.test_package_descriptor import _descriptor, _identities


def test_linear_history_uses_signed_parent_links_not_largest_version(
    tmp_path: Path,
) -> None:
    _administrator, member, manifest, _key = _identities(tmp_path)
    first = _descriptor(
        manifest,
        member,
        project_version=100,
        workshop_item_id="1001",
    )
    second = _descriptor(
        manifest,
        member,
        project_version=2,
        workshop_item_id="1002",
        version_id="bbbbbbbb-1234-4678-9234-567812345678",
        parent_descriptor_hash=first.descriptor_hash,
    )

    lineage = SteamPackageLineage.resolve(first.project_uuid, [second, first])

    assert lineage.require_single_head() == second
    assert not lineage.forked
    assert not lineage.incomplete


def test_siblings_from_same_parent_are_an_explicit_fork(tmp_path: Path) -> None:
    _administrator, member, manifest, _key = _identities(tmp_path)
    parent = _descriptor(manifest, member, workshop_item_id="1001")
    left = _descriptor(
        manifest,
        member,
        workshop_item_id="1002",
        version_id="bbbbbbbb-1234-4678-9234-567812345678",
        parent_descriptor_hash=parent.descriptor_hash,
    )
    right = _descriptor(
        manifest,
        member,
        workshop_item_id="1003",
        version_id="cccccccc-1234-4678-9234-567812345678",
        parent_descriptor_hash=parent.descriptor_hash,
    )

    lineage = SteamPackageLineage.resolve(
        parent.project_uuid,
        [parent, left, right],
    )

    assert set(lineage.heads) == {left, right}
    assert lineage.fork_parent_hashes == (parent.descriptor_hash,)
    with pytest.raises(SteamPackageForkError, match="competing"):
        lineage.require_single_head()


def test_missing_parent_blocks_automatic_head_selection(tmp_path: Path) -> None:
    _administrator, member, manifest, _key = _identities(tmp_path)
    descriptor = _descriptor(
        manifest,
        member,
        parent_descriptor_hash="d" * 64,
    )

    lineage = SteamPackageLineage.resolve(descriptor.project_uuid, [descriptor])

    assert lineage.incomplete
    with pytest.raises(SteamPackageForkError, match="incomplete"):
        lineage.require_single_head()
