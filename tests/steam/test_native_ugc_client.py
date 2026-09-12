import ctypes
from pathlib import Path

import pytest

from app.steam.constants import SAVESHIFT_STEAM_APP_ID
from app.steam.errors import SteamworksError, SteamworksUnavailableError
from app.steam.native_ugc_client import (
    _CREATE_ITEM_CALLBACK,
    _DELETE_ITEM_CALLBACK,
    _DOWNLOAD_ITEM_CALLBACK,
    _LOBBY_CREATED_CALLBACK,
    _LOBBY_ENTER_CALLBACK,
    _GAME_LOBBY_JOIN_REQUESTED_CALLBACK,
    _LOBBY_CHAT_MESSAGE_CALLBACK,
    _CallbackMessage,
    _DownloadItemResult,
    _GameLobbyJoinRequested,
    _LobbyChatMessage,
    _SUBMIT_ITEM_UPDATE_CALLBACK,
    SteamworksUgcClient,
)
from app.steam.ugc_client import SteamUgcVisibility


class FakeFunction:
    def __init__(self, result: object = None) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *args: object) -> object:
        self.calls.append(args)

        if callable(self.result):
            return self.result(*args)

        return self.result


class FakeSteamApi:
    def __init__(self, install_directory: Path) -> None:
        self.SteamAPI_InitFlat = FakeFunction(0)
        self.SteamAPI_Shutdown = FakeFunction()
        self.SteamAPI_GetHSteamPipe = FakeFunction(8)
        self.SteamAPI_ManualDispatch_Init = FakeFunction()
        self.SteamAPI_ManualDispatch_RunFrame = FakeFunction()
        self.SteamAPI_ManualDispatch_GetNextCallback = FakeFunction(False)
        self.SteamAPI_ManualDispatch_FreeLastCallback = FakeFunction()
        self.SteamAPI_ManualDispatch_GetAPICallResult = FakeFunction(True)
        self.SteamAPI_SteamUGC_v021 = FakeFunction(1234)
        self.SteamAPI_SteamUser_v023 = FakeFunction(2234)
        self.SteamAPI_SteamFriends_v018 = FakeFunction(3234)
        self.SteamAPI_SteamMatchmaking_v009 = FakeFunction(4234)
        self.SteamAPI_ISteamUser_GetSteamID = FakeFunction(76561198000000001)
        self.SteamAPI_ISteamFriends_GetPersonaName = FakeFunction(b"Jake")
        self.SteamAPI_ISteamFriends_GetFriendCount = FakeFunction(2)
        self.SteamAPI_ISteamFriends_GetFriendByIndex = FakeFunction(
            lambda _friends, index, _flags: 76561198000000002 + index
        )
        self.SteamAPI_ISteamFriends_GetFriendPersonaName = FakeFunction(
            lambda _friends, steam_id: (
                b"Hunter" if steam_id == 76561198000000002 else b"Dad"
            )
        )
        self.SteamAPI_ISteamFriends_ActivateGameOverlayInviteDialog = FakeFunction()
        self.SteamAPI_ISteamMatchmaking_CreateLobby = FakeFunction(500)
        self.SteamAPI_ISteamMatchmaking_JoinLobby = FakeFunction(600)
        self.SteamAPI_ISteamMatchmaking_LeaveLobby = FakeFunction()
        self.SteamAPI_ISteamMatchmaking_InviteUserToLobby = FakeFunction(True)
        self.SteamAPI_ISteamMatchmaking_GetNumLobbyMembers = FakeFunction(2)
        self.SteamAPI_ISteamMatchmaking_GetLobbyMemberByIndex = FakeFunction(
            lambda _matchmaking, _lobby, index: 76561198000000001 + index
        )
        self.SteamAPI_ISteamMatchmaking_GetLobbyData = FakeFunction(b"group-123")
        self.SteamAPI_ISteamMatchmaking_SetLobbyData = FakeFunction(True)
        self.SteamAPI_ISteamMatchmaking_GetLobbyOwner = FakeFunction(
            76561198000000001
        )
        self.SteamAPI_ISteamMatchmaking_SendLobbyChatMsg = FakeFunction(True)
        self.SteamAPI_ISteamMatchmaking_GetLobbyChatEntry = FakeFunction(0)
        self.SteamAPI_ISteamUGC_CreateItem = FakeFunction(100)
        self.SteamAPI_ISteamUGC_StartItemUpdate = FakeFunction(200)
        self.SteamAPI_ISteamUGC_SetItemTitle = FakeFunction(True)
        self.SteamAPI_ISteamUGC_SetItemDescription = FakeFunction(True)
        self.SteamAPI_ISteamUGC_SetItemMetadata = FakeFunction(True)
        self.SteamAPI_ISteamUGC_SetItemVisibility = FakeFunction(True)
        self.SteamAPI_ISteamUGC_SetItemContent = FakeFunction(True)
        self.SteamAPI_ISteamUGC_SubmitItemUpdate = FakeFunction(300)
        self.SteamAPI_ISteamUGC_DownloadItem = FakeFunction(True)
        self.SteamAPI_ISteamUGC_GetItemState = FakeFunction(0)
        self.SteamAPI_ISteamUGC_GetItemInstallInfo = FakeFunction(
            self._install_info
        )
        self.SteamAPI_ISteamUGC_DeleteItem = FakeFunction(400)
        self.install_directory = install_directory

    def _install_info(
        self,
        _ugc: object,
        _published_file_id: object,
        size_on_disk: object,
        folder: object,
        _folder_size: object,
        timestamp: object,
    ) -> bool:
        ctypes.cast(
            size_on_disk,
            ctypes.POINTER(ctypes.c_uint64),
        ).contents.value = 123
        folder.value = str(self.install_directory).encode("utf-8")
        ctypes.cast(
            timestamp,
            ctypes.POINTER(ctypes.c_uint32),
        ).contents.value = 456
        return True


class StubbedResultClient(SteamworksUgcClient):
    def _await_call(
        self,
        api_call: int,
        result_type: type[ctypes.Structure],
        expected_callback: int,
    ) -> ctypes.Structure:
        result = result_type()
        result.result = 1

        if expected_callback == _CREATE_ITEM_CALLBACK:
            result.published_file_id = 987654321
            result.needs_legal_agreement = True
        elif expected_callback == _SUBMIT_ITEM_UPDATE_CALLBACK:
            result.published_file_id = 987654321
            result.needs_legal_agreement = False
        elif expected_callback == _DELETE_ITEM_CALLBACK:
            result.published_file_id = 987654321
        elif expected_callback == _LOBBY_CREATED_CALLBACK:
            result.lobby_id = 109775240917155001
        elif expected_callback == _LOBBY_ENTER_CALLBACK:
            result.lobby_id = 109775240917155001
            result.chat_room_enter_response = 1
        else:
            raise AssertionError(f"Unexpected callback: {expected_callback}")

        return result

    def _await_download(self, published_file_id: int) -> None:
        assert published_file_id == 987654321


class RecoveringDownloadClient(SteamworksUgcClient):
    def __init__(self, *args: object, **kwargs: object) -> None:
        self._sent_transient_callback = False
        super().__init__(*args, **kwargs)

    def _next_callbacks(self) -> list[_CallbackMessage]:
        if self._sent_transient_callback:
            return []

        self._sent_transient_callback = True
        result = _DownloadItemResult(
            app_id=SAVESHIFT_STEAM_APP_ID,
            published_file_id=987654321,
            result=3,
        )
        message = _CallbackMessage(
            steam_user=1,
            callback_id=_DOWNLOAD_ITEM_CALLBACK,
            parameter=ctypes.cast(
                ctypes.pointer(result),
                ctypes.POINTER(ctypes.c_uint8),
            ),
            parameter_size=ctypes.sizeof(result),
        )
        message._parameter_copy = result
        return [message]


class SocialEventClient(SteamworksUgcClient):
    def __init__(self, *args: object, **kwargs: object) -> None:
        self._events_sent = False
        super().__init__(*args, **kwargs)

    def _next_callbacks(self) -> list[_CallbackMessage]:
        if self._events_sent:
            return []
        self._events_sent = True
        request = _GameLobbyJoinRequested(
            lobby_id=109775240917155001,
            friend_steam_id=76561198000000002,
        )
        chat = _LobbyChatMessage(
            lobby_id=109775240917155001,
            sender_steam_id=76561198000000002,
            chat_entry_type=1,
            chat_id=7,
        )
        messages = [
            _CallbackMessage(
                steam_user=1,
                callback_id=_GAME_LOBBY_JOIN_REQUESTED_CALLBACK,
                parameter=ctypes.cast(
                    ctypes.pointer(request), ctypes.POINTER(ctypes.c_uint8)
                ),
                parameter_size=ctypes.sizeof(request),
            ),
            _CallbackMessage(
                steam_user=1,
                callback_id=_LOBBY_CHAT_MESSAGE_CALLBACK,
                parameter=ctypes.cast(
                    ctypes.pointer(chat), ctypes.POINTER(ctypes.c_uint8)
                ),
                parameter_size=ctypes.sizeof(chat),
            ),
        ]
        messages[0]._parameter_copy = request
        messages[1]._parameter_copy = chat
        return messages


def test_native_client_initializes_and_shuts_down(tmp_path: Path) -> None:
    api = FakeSteamApi(tmp_path)

    client = StubbedResultClient(library=api)
    client.close()

    assert len(api.SteamAPI_InitFlat.calls) == 1
    assert len(api.SteamAPI_ManualDispatch_Init.calls) == 1
    assert len(api.SteamAPI_Shutdown.calls) == 1


def test_publish_configures_and_submits_unlisted_item(tmp_path: Path) -> None:
    api = FakeSteamApi(tmp_path)
    client = StubbedResultClient(library=api)
    content = tmp_path / "content"
    content.mkdir()

    result = client.publish_item(
        content,
        title="Package title",
        description="Package description",
        metadata='{"schema":1}',
        visibility=SteamUgcVisibility.UNLISTED,
    )

    assert result.published_file_id == "987654321"
    assert result.user_needs_legal_agreement is True
    assert api.SteamAPI_ISteamUGC_CreateItem.calls == [
        (1234, SAVESHIFT_STEAM_APP_ID, 0)
    ]
    assert api.SteamAPI_ISteamUGC_SetItemVisibility.calls == [
        (1234, 200, int(SteamUgcVisibility.UNLISTED))
    ]
    assert api.SteamAPI_ISteamUGC_SetItemContent.calls == [
        (1234, 200, str(content.resolve()).encode("utf-8"))
    ]
    assert api.SteamAPI_ISteamUGC_SubmitItemUpdate.calls == [
        (1234, 200, b"Save Shift package upload")
    ]


def test_failed_publish_removes_created_item(tmp_path: Path) -> None:
    api = FakeSteamApi(tmp_path)
    api.SteamAPI_ISteamUGC_SetItemMetadata.result = False
    client = StubbedResultClient(library=api)
    content = tmp_path / "content"
    content.mkdir()

    with pytest.raises(SteamworksError, match="set Workshop metadata"):
        client.publish_item(
            content,
            title="Package title",
            description="Package description",
            metadata="{}",
            visibility=SteamUgcVisibility.UNLISTED,
        )

    assert api.SteamAPI_ISteamUGC_DeleteItem.calls == [(1234, 987654321)]


def test_update_reuses_existing_workshop_item(tmp_path: Path) -> None:
    api = FakeSteamApi(tmp_path)
    client = StubbedResultClient(library=api)
    content = tmp_path / "manifest"
    content.mkdir()

    result = client.update_item(
        "987654321",
        content,
        title="Save Shift Group: Family",
        description="Signed group manifest",
        metadata='{"revision":2}',
        visibility=SteamUgcVisibility.UNLISTED,
    )

    assert result.published_file_id == "987654321"
    assert api.SteamAPI_ISteamUGC_CreateItem.calls == []
    assert api.SteamAPI_ISteamUGC_StartItemUpdate.calls == [
        (1234, SAVESHIFT_STEAM_APP_ID, 987654321)
    ]
    assert api.SteamAPI_ISteamUGC_SubmitItemUpdate.calls == [
        (1234, 200, b"Save Shift group manifest update")
    ]


def test_download_waits_then_returns_installed_directory(tmp_path: Path) -> None:
    install_directory = tmp_path / "installed"
    install_directory.mkdir()
    api = FakeSteamApi(install_directory)
    client = StubbedResultClient(library=api)

    result = client.download_item("987654321")

    assert result == install_directory
    assert api.SteamAPI_ISteamUGC_DownloadItem.calls == [
        (1234, 987654321, True)
    ]


def test_download_recovers_when_steam_installs_after_transient_error(
    tmp_path: Path,
) -> None:
    install_directory = tmp_path / "installed"
    install_directory.mkdir()
    api = FakeSteamApi(install_directory)
    states = iter([8, 4])
    api.SteamAPI_ISteamUGC_GetItemState.result = lambda *_args: next(states, 4)
    client = RecoveringDownloadClient(
        library=api,
        download_timeout_seconds=1.0,
    )

    result = client.download_item("987654321")

    assert result == install_directory
    assert len(api.SteamAPI_ISteamUGC_GetItemState.calls) >= 2


def test_delete_waits_for_matching_confirmation(tmp_path: Path) -> None:
    api = FakeSteamApi(tmp_path)
    client = StubbedResultClient(library=api)

    client.delete_item("987654321")

    assert api.SteamAPI_ISteamUGC_DeleteItem.calls == [(1234, 987654321)]


def test_social_identity_and_friends_use_authenticated_steam_account(
    tmp_path: Path,
) -> None:
    api = FakeSteamApi(tmp_path)
    client = StubbedResultClient(library=api)

    assert client.current_identity().steam_id == "76561198000000001"
    assert client.current_identity().persona_name == "Jake"
    assert [(friend.steam_id, friend.persona_name) for friend in client.list_friends()] == [
        ("76561198000000002", "Hunter"),
        ("76561198000000003", "Dad"),
    ]


def test_private_lobby_supports_metadata_invites_and_members(tmp_path: Path) -> None:
    api = FakeSteamApi(tmp_path)
    client = StubbedResultClient(library=api)

    lobby = client.create_private_lobby(metadata={"saveshift_group": "group-123"})
    client.invite_friend(lobby.lobby_id, "76561198000000002")
    client.open_invite_overlay(lobby.lobby_id)

    assert lobby.lobby_id == "109775240917155001"
    assert client.lobby_data(lobby.lobby_id, "saveshift_group") == "group-123"
    assert client.lobby_members(lobby.lobby_id) == [
        "76561198000000001",
        "76561198000000002",
    ]
    assert api.SteamAPI_ISteamMatchmaking_SetLobbyData.calls == [
        (4234, 109775240917155001, b"saveshift_group", b"group-123")
    ]
    assert api.SteamAPI_ISteamMatchmaking_InviteUserToLobby.calls == [
        (4234, 109775240917155001, 76561198000000002)
    ]
    assert api.SteamAPI_ISteamFriends_ActivateGameOverlayInviteDialog.calls == [
        (3234, 109775240917155001)
    ]


def test_join_and_leave_private_lobby(tmp_path: Path) -> None:
    api = FakeSteamApi(tmp_path)
    client = StubbedResultClient(library=api)

    lobby = client.join_lobby("109775240917155001")
    client.leave_lobby(lobby.lobby_id)

    assert api.SteamAPI_ISteamMatchmaking_JoinLobby.calls == [
        (4234, 109775240917155001)
    ]
    assert api.SteamAPI_ISteamMatchmaking_LeaveLobby.calls == [
        (4234, 109775240917155001)
    ]


def test_lobby_owner_and_binary_message_use_steam_chat(tmp_path: Path) -> None:
    api = FakeSteamApi(tmp_path)
    client = StubbedResultClient(library=api)

    assert client.lobby_owner("109775240917155001") == "76561198000000001"
    client.send_lobby_message("109775240917155001", b'{"kind":"join"}')

    call = api.SteamAPI_ISteamMatchmaking_SendLobbyChatMsg.calls[0]
    assert call[0:2] == (4234, 109775240917155001)
    assert ctypes.string_at(call[2], call[3]) == b'{"kind":"join"}'


def test_poll_social_events_returns_join_request_and_chat_payload(
    tmp_path: Path,
) -> None:
    api = FakeSteamApi(tmp_path)
    payload = b'{"kind":"join-request"}'

    def read_chat(
        _matchmaking,
        _lobby_id,
        chat_id,
        sender,
        destination,
        _capacity,
        entry_type,
    ) -> int:
        assert chat_id == 7
        ctypes.cast(sender, ctypes.POINTER(ctypes.c_uint64)).contents.value = (
            76561198000000002
        )
        ctypes.cast(entry_type, ctypes.POINTER(ctypes.c_int)).contents.value = 1
        ctypes.memmove(destination, payload, len(payload))
        return len(payload)

    api.SteamAPI_ISteamMatchmaking_GetLobbyChatEntry.result = read_chat
    client = SocialEventClient(library=api)

    events = client.poll_social_events()

    assert events[0].lobby_id == "109775240917155001"
    assert events[0].friend_steam_id == "76561198000000002"
    assert events[1].sender_steam_id == "76561198000000002"
    assert events[1].payload == payload


def test_social_callback_is_preserved_while_another_operation_runs(
    tmp_path: Path,
) -> None:
    api = FakeSteamApi(tmp_path)
    client = StubbedResultClient(library=api)
    request = _GameLobbyJoinRequested(
        lobby_id=109775240917155001,
        friend_steam_id=76561198000000002,
    )
    message = _CallbackMessage(
        steam_user=1,
        callback_id=_GAME_LOBBY_JOIN_REQUESTED_CALLBACK,
        parameter=ctypes.cast(
            ctypes.pointer(request), ctypes.POINTER(ctypes.c_uint8)
        ),
        parameter_size=ctypes.sizeof(request),
    )
    message._parameter_copy = request

    client._preserve_social_callback(message)

    assert client.poll_social_events()[0].friend_steam_id == "76561198000000002"


def test_initialization_failure_uses_steam_error_message(tmp_path: Path) -> None:
    api = FakeSteamApi(tmp_path)

    def fail_initialization(error_message: object) -> int:
        error_message.value = b"Steam client is unavailable"
        return 2

    api.SteamAPI_InitFlat.result = fail_initialization

    with pytest.raises(
        SteamworksUnavailableError,
        match="Steam client is unavailable",
    ):
        StubbedResultClient(library=api)


def test_resolve_dll_path_uses_explicit_file(tmp_path: Path) -> None:
    dll_path = tmp_path / "steam_api64.dll"
    dll_path.write_bytes(b"test")

    assert SteamworksUgcClient.resolve_dll_path(dll_path) == dll_path.resolve()


def test_invalid_parameter_result_explains_workshop_configuration() -> None:
    with pytest.raises(
        SteamworksError,
        match="unpublished Workshop file-transfer configuration",
    ):
        SteamworksUgcClient._require_ok("upload Workshop item", 8)


def test_stalled_download_logs_waiting_and_timeout(tmp_path, monkeypatch, caplog):
    import logging
    import itertools
    import app.steam.native_ugc_client as native

    clock = itertools.count()
    monkeypatch.setattr(native.time, "monotonic", lambda: float(next(clock)))
    monkeypatch.setattr(native.time, "sleep", lambda _: None)
    client = SteamworksUgcClient(library=FakeSteamApi(tmp_path), download_timeout_seconds=45)
    with caplog.at_level(logging.INFO, logger="SaveShift"):
        with pytest.raises(SteamworksError, match="timed out"):
            client.download_item("987654321")
    assert "state=0" in caplog.text
    assert 1 <= caplog.text.count("steam.download waiting") <= 4
    assert "steam.download timeout" in caplog.text
    assert "error_type=SteamworksError" in caplog.text


def test_download_default_timeout_is_one_minute_without_shortening_uploads(tmp_path):
    client = SteamworksUgcClient(library=FakeSteamApi(tmp_path))
    assert client.download_timeout_seconds == 60.0
    assert client.timeout_seconds == 300.0
    client.close()


def test_default_download_times_out_after_one_minute(tmp_path, monkeypatch, caplog):
    import logging
    import app.steam.native_ugc_client as native

    now = [0.0]
    monkeypatch.setattr(native.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(native.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    client = SteamworksUgcClient(library=FakeSteamApi(tmp_path))
    with caplog.at_level(logging.INFO, logger="SaveShift"):
        with pytest.raises(SteamworksError, match="timed out"):
            client.download_item("987654321")
    assert 60.0 <= now[0] < 60.1
    assert "timeout=60.0s" in caplog.text
    client.close()
