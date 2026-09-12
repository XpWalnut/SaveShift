from datetime import UTC, datetime, timedelta

import pytest

from app.coordination.cloudflare_provisioning import CreatedGroup
from app.coordination.models import GroupInvitation, GroupLeaveResult, PairedDevice
from app.coordination.setup_controller import GroupLeaveOutcome, GroupSetupController


def test_setup_controller_creates_group_off_ui_thread(qtbot) -> None:
    created = CreatedGroup(
        provider_url="https://group.workers.dev",
        account_id="account-123",
        script_name="saveshift-coordination",
        device=PairedDevice("device-123", "device-token", True),
    )

    class FakeCreator:
        def create_group(self, device_name: str):
            assert device_name == "Gaming PC"
            return created

    controller = GroupSetupController(
        creator_factory=lambda: FakeCreator(),
    )

    with qtbot.waitSignal(controller.create_completed, timeout=2000) as signal:
        assert controller.create_group("Gaming PC")

    assert signal.args == [created]
    qtbot.waitUntil(lambda: not controller.running, timeout=2000)


def test_setup_controller_creates_steam_group_off_ui_thread(qtbot) -> None:
    created = object()

    class FakeSteamService:
        def create_group(self, name: str):
            assert name == "Family Worlds"
            return created

    controller = GroupSetupController(
        steam_service_factory=FakeSteamService,
    )
    with qtbot.waitSignal(controller.steam_create_completed) as signal:
        assert controller.create_steam_group("Family Worlds")

    assert signal.args == [created]
    assert not controller.running


def test_setup_controller_joins_group_off_ui_thread(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invitation = GroupInvitation(
        provider_url="https://group.workers.dev",
        invitation_token="invite-token",
        expires_at_utc=datetime.now(UTC) + timedelta(hours=1),
    )
    joined = PairedDevice("device-123", "device-token", False)

    class FakeProvider:
        def __init__(self, provider_url: str) -> None:
            assert provider_url == invitation.provider_url

        def join(self, invitation_token: str, device_name: str):
            assert (invitation_token, device_name) == (
                "invite-token",
                "Friend PC",
            )
            return joined

    monkeypatch.setattr(
        "app.coordination.setup_controller.HttpCoordinationProvider",
        FakeProvider,
    )
    controller = GroupSetupController()

    with qtbot.waitSignal(controller.join_completed, timeout=2000) as signal:
        assert controller.join_group(invitation, "Friend PC")

    assert signal.args == [invitation, joined]
    qtbot.waitUntil(lambda: not controller.running, timeout=2000)


def test_setup_controller_leaves_and_removes_empty_cloudflare_group(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    removals: list[tuple[str, str]] = []

    class FakeProvider:
        def __init__(self, provider_url: str, device_token: str) -> None:
            assert provider_url == "https://group.workers.dev"
            assert device_token == "device-token"

        def leave_group(self):
            return GroupLeaveResult(group_empty=True)

    class FakeRemover:
        def remove(self, account_id: str, script_name: str) -> None:
            removals.append((account_id, script_name))

    monkeypatch.setattr(
        "app.coordination.setup_controller.HttpCoordinationProvider",
        FakeProvider,
    )
    controller = GroupSetupController(remover_factory=lambda: FakeRemover())

    with qtbot.waitSignal(controller.leave_completed, timeout=2000) as signal:
        assert controller.leave_group(
            "https://group.workers.dev",
            "device-token",
            account_id="account-123",
            script_name="saveshift-coordination-123",
        )

    assert signal.args == [GroupLeaveOutcome(True, True, "")]
    assert removals == [("account-123", "saveshift-coordination-123")]
    qtbot.waitUntil(lambda: not controller.running, timeout=2000)
