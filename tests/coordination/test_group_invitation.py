from datetime import UTC, datetime

import pytest

from app.coordination.models import GroupInvitation


def test_group_invitation_round_trips_without_exposing_json_fields() -> None:
    invitation = GroupInvitation(
        provider_url="https://group.example.workers.dev",
        invitation_token="single-use-secret",
        expires_at_utc=datetime(2026, 7, 15, 12, tzinfo=UTC),
    )

    encoded = invitation.to_text()

    assert encoded.startswith("saveshift-invite-v1:")
    assert "single-use-secret" not in encoded
    assert GroupInvitation.from_text(encoded) == invitation


@pytest.mark.parametrize(
    "value",
    [
        "not-an-invitation",
        "saveshift-invite-v1:not-base64!",
    ],
)
def test_group_invitation_rejects_malformed_text(value: str) -> None:
    with pytest.raises(ValueError):
        GroupInvitation.from_text(value)


def test_group_invitation_rejects_untrusted_provider_url() -> None:
    invitation = GroupInvitation(
        provider_url="http://provider.example.com",
        invitation_token="secret",
        expires_at_utc=datetime(2026, 7, 15, 12, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="provider URL"):
        GroupInvitation.from_text(invitation.to_text())
