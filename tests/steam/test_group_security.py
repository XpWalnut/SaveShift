from datetime import UTC, datetime
from pathlib import Path
import os
import uuid

import pytest
from cryptography.exceptions import InvalidTag

from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_security import (
    SteamGroupKeyEnvelope,
    SteamMembershipCertificate,
)
from tests.steam.test_device_identity import MemoryProtector


def _identity(tmp_path: Path, name: str, steam_id: str):
    return SteamDeviceIdentityStore(
        tmp_path / f"{name}.json",
        protector=MemoryProtector(),
    ).load_or_create(steam_id)


def test_administrator_issues_verifiable_member_certificate(tmp_path: Path) -> None:
    administrator = _identity(tmp_path, "administrator", "76561198000000001")
    member = _identity(tmp_path, "member", "76561198000000002")
    group_id = str(uuid.uuid4())

    certificate = SteamMembershipCertificate.issue(
        group_id=group_id,
        member=member,
        administrator=administrator,
        issued_at=datetime(2026, 9, 12, tzinfo=UTC),
    )
    restored = SteamMembershipCertificate.from_dict(certificate.to_dict())

    assert restored.verify(administrator.signing_public_key)
    assert restored.group_id == group_id
    assert restored.steam_id == member.steam_id


def test_modified_member_certificate_is_rejected(tmp_path: Path) -> None:
    administrator = _identity(tmp_path, "administrator", "76561198000000001")
    member = _identity(tmp_path, "member", "76561198000000002")
    certificate = SteamMembershipCertificate.issue(
        group_id=str(uuid.uuid4()), member=member, administrator=administrator
    )
    changed = certificate.to_dict()
    changed["steam_id"] = "76561198000000003"

    assert not SteamMembershipCertificate.from_dict(changed).verify(
        administrator.signing_public_key
    )


def test_group_key_envelope_only_opens_for_recipient(tmp_path: Path) -> None:
    member = _identity(tmp_path, "member", "76561198000000002")
    stranger = _identity(tmp_path, "stranger", "76561198000000003")
    group_key = os.urandom(32)
    envelope = SteamGroupKeyEnvelope.seal(
        group_id=str(uuid.uuid4()),
        key_epoch=1,
        recipient_device_id=member.device_id,
        recipient_agreement_public_key=member.agreement_public_key,
        group_key=group_key,
    )

    assert envelope.open(member) == group_key
    with pytest.raises(ValueError, match="another device"):
        envelope.open(stranger)


def test_group_key_envelope_detects_metadata_tampering(tmp_path: Path) -> None:
    member = _identity(tmp_path, "member", "76561198000000002")
    envelope = SteamGroupKeyEnvelope.seal(
        group_id=str(uuid.uuid4()),
        key_epoch=1,
        recipient_device_id=member.device_id,
        recipient_agreement_public_key=member.agreement_public_key,
        group_key=os.urandom(32),
    )
    tampered = SteamGroupKeyEnvelope(
        **{**envelope.to_dict(), "key_epoch": 2}
    )

    with pytest.raises(InvalidTag):
        tampered.open(member)
