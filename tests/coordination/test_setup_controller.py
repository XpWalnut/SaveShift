from datetime import UTC, datetime, timedelta

import pytest

from app.coordination.cloudflare_provisioning import CreatedGroup
from app.coordination.models import GroupInvitation, GroupLeaveResult, PairedDevice
from app.coordination.setup_controller import GroupLeaveOutcome, GroupSetupController
from app.steam.device_identity import SteamDeviceIdentityStore
from app.steam.group_manifest import SteamGroupManifest
from app.steam.social_client import SteamIdentity
from app.steam.social_client import SteamFriend
from tests.steam.test_device_identity import MemoryProtector


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


def test_setup_controller_loads_steam_friends_off_ui_thread(qtbot) -> None:
    friends = [SteamFriend("76561198000000002", "Hunter")]

    class FakeSteamClient:
        closed = False

        def list_friends(self):
            return friends

        def close(self) -> None:
            self.closed = True

    client = FakeSteamClient()
    controller = GroupSetupController(steam_client_factory=lambda: client)

    with qtbot.waitSignal(controller.steam_friends_loaded) as signal:
        assert controller.load_steam_friends()

    assert signal.args == [friends]
    assert client.closed
    assert not controller.running


def test_setup_controller_lists_and_revokes_steam_member(
    qtbot,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity_store = SteamDeviceIdentityStore(
        tmp_path / "administrator.json",
        protector=MemoryProtector(),
    )
    administrator = identity_store.load_or_create("76561198000000001")
    member = SteamDeviceIdentityStore(
        tmp_path / "member.json",
        protector=MemoryProtector(),
    ).load_or_create("76561198000000002")
    manifest, group_key = SteamGroupManifest.create("Friends", administrator)
    state = {"manifest": manifest.add_member(member, group_key, administrator)}

    class FakeSteamClient:
        def current_identity(self):
            return SteamIdentity(administrator.steam_id, "Administrator")

        def list_friends(self):
            return [SteamFriend(member.steam_id, "Hunter")]

        def close(self) -> None:
            pass

    class FakeTransport:
        def __init__(self, _client, cache=None) -> None:
            pass

        def download(self, item_id: str):
            assert item_id == "3797671909"
            return state["manifest"]

        def update(self, item_id: str, updated: SteamGroupManifest) -> None:
            assert item_id == "3797671909"
            state["manifest"] = updated

    monkeypatch.setattr(
        "app.coordination.setup_controller.SteamGroupManifestTransport",
        FakeTransport,
    )
    controller = GroupSetupController(
        steam_client_factory=FakeSteamClient,
        identity_store_factory=lambda: identity_store,
        manifest_cache_factory=lambda: object(),
    )

    with qtbot.waitSignal(controller.steam_members_loaded) as listed:
        assert controller.load_steam_group_members(
            "3797671909",
            state["manifest"].group_id,
        )

    assert listed.args[0][0].persona_name == "Hunter"
    assert listed.args[0][0].device_id == member.device_id

    with qtbot.waitSignal(controller.steam_member_revoked) as revoked:
        assert controller.revoke_steam_member(
            "3797671909",
            state["manifest"].group_id,
            member.device_id,
        )

    updated = revoked.args[0]
    assert updated.key_epoch == 2
    assert [item.device_id for item in updated.active_members] == [
        administrator.device_id
    ]
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
