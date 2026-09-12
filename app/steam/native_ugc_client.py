import ctypes
import os
import sys
import threading
import time
from pathlib import Path
from typing import Mapping

from app.core.logging import diagnostic_operation, logger
from app.steam.constants import SAVESHIFT_STEAM_APP_ID
from app.steam.errors import SteamworksError, SteamworksUnavailableError
from app.steam.ugc_client import (
    SteamPublishedItem,
    SteamUgcVisibility,
)
from app.steam.social_client import (
    SteamFriend,
    SteamIdentity,
    SteamLobby,
    SteamLobbyJoinRequest,
    SteamLobbyMessage,
    SteamSocialEvent,
)


_RESULT_OK = 1
_WORKSHOP_FILE_TYPE_COMMUNITY = 0
_INVALID_UPDATE_HANDLE = 0xFFFFFFFFFFFFFFFF
_STEAM_API_CALL_COMPLETED_CALLBACK = 703
_CREATE_ITEM_CALLBACK = 3403
_SUBMIT_ITEM_UPDATE_CALLBACK = 3404
_DOWNLOAD_ITEM_CALLBACK = 3406
_DELETE_ITEM_CALLBACK = 3417
_LOBBY_ENTER_CALLBACK = 504
_LOBBY_CREATED_CALLBACK = 513
_GAME_LOBBY_JOIN_REQUESTED_CALLBACK = 333
_LOBBY_CHAT_MESSAGE_CALLBACK = 507
_ITEM_STATE_INSTALLED = 4
_ITEM_STATE_NEEDS_UPDATE = 8
_ITEM_STATE_DOWNLOADING = 16
_ITEM_STATE_DOWNLOAD_PENDING = 32
_TRANSIENT_DOWNLOAD_RESULTS = {2, 3, 16, 20, 50, 53}
_FRIEND_FLAG_IMMEDIATE = 0x04
_LOBBY_TYPE_PRIVATE = 0
_CHAT_ROOM_ENTER_SUCCESS = 1
_CHAT_ENTRY_TYPE_MESSAGE = 1
_MAX_LOBBY_MESSAGE_BYTES = 4000

_RESULT_MESSAGES = {
    2: "generic failure",
    3: "no connection",
    5: "invalid password",
    8: "invalid parameter or unpublished Workshop file-transfer configuration",
    9: "file not found",
    15: "access denied",
    16: "operation timed out",
    20: "service unavailable",
    25: "request limit exceeded",
    33: "account not logged on",
    50: "duplicate request",
    53: "service temporarily read-only",
}


class _CallbackMessage(ctypes.Structure):
    _fields_ = [
        ("steam_user", ctypes.c_int32),
        ("callback_id", ctypes.c_int),
        ("parameter", ctypes.POINTER(ctypes.c_uint8)),
        ("parameter_size", ctypes.c_int),
    ]


class _ApiCallCompleted(ctypes.Structure):
    _fields_ = [
        ("api_call", ctypes.c_uint64),
        ("callback_id", ctypes.c_int),
        ("parameter_size", ctypes.c_uint32),
    ]


class _CreateItemResult(ctypes.Structure):
    _fields_ = [
        ("result", ctypes.c_int),
        ("published_file_id", ctypes.c_uint64),
        ("needs_legal_agreement", ctypes.c_bool),
    ]


class _SubmitItemUpdateResult(ctypes.Structure):
    _fields_ = [
        ("result", ctypes.c_int),
        ("needs_legal_agreement", ctypes.c_bool),
        ("published_file_id", ctypes.c_uint64),
    ]


class _DownloadItemResult(ctypes.Structure):
    _fields_ = [
        ("app_id", ctypes.c_uint32),
        ("published_file_id", ctypes.c_uint64),
        ("result", ctypes.c_int),
    ]


class _DeleteItemResult(ctypes.Structure):
    _fields_ = [
        ("result", ctypes.c_int),
        ("published_file_id", ctypes.c_uint64),
    ]


class _LobbyCreatedResult(ctypes.Structure):
    _fields_ = [
        ("result", ctypes.c_int),
        ("lobby_id", ctypes.c_uint64),
    ]


class _LobbyEnterResult(ctypes.Structure):
    _fields_ = [
        ("lobby_id", ctypes.c_uint64),
        ("chat_permissions", ctypes.c_uint32),
        ("locked", ctypes.c_bool),
        ("chat_room_enter_response", ctypes.c_uint32),
    ]


class _GameLobbyJoinRequested(ctypes.Structure):
    _fields_ = [
        ("lobby_id", ctypes.c_uint64),
        ("friend_steam_id", ctypes.c_uint64),
    ]


class _LobbyChatMessage(ctypes.Structure):
    _fields_ = [
        ("lobby_id", ctypes.c_uint64),
        ("sender_steam_id", ctypes.c_uint64),
        ("chat_entry_type", ctypes.c_uint8),
        ("chat_id", ctypes.c_uint32),
    ]


class SteamworksUgcClient:
    """Thin ctypes binding over the official Steamworks flat UGC API."""

    def __init__(
        self,
        dll_path: Path | None = None,
        *,
        timeout_seconds: float = 300.0,
        download_timeout_seconds: float = 60.0,
        library: object | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.download_timeout_seconds = download_timeout_seconds
        self._lock = threading.RLock()
        self._closed = False
        self._pending_social_callbacks: list[_CallbackMessage] = []

        if library is None:
            resolved_path = self.resolve_dll_path(dll_path)

            try:
                library = ctypes.CDLL(str(resolved_path))
            except OSError as error:
                raise SteamworksUnavailableError(
                    f"Steamworks could not load {resolved_path}: {error}"
                ) from error

        self._api = library
        self._configure_signatures()
        error_message = ctypes.create_string_buffer(1024)
        init_result = self._api.SteamAPI_InitFlat(error_message)

        if init_result != 0:
            message = error_message.value.decode("utf-8", errors="replace").strip()
            raise SteamworksUnavailableError(
                message or f"Steamworks initialization failed ({init_result})."
            )

        self._api.SteamAPI_ManualDispatch_Init()
        self._pipe = int(self._api.SteamAPI_GetHSteamPipe())
        self._ugc = self._api.SteamAPI_SteamUGC_v021()
        self._user = self._api.SteamAPI_SteamUser_v023()
        self._friends = self._api.SteamAPI_SteamFriends_v018()
        self._matchmaking = self._api.SteamAPI_SteamMatchmaking_v009()

        if (
            self._pipe == 0
            or not self._ugc
            or not self._user
            or not self._friends
            or not self._matchmaking
        ):
            self.close()
            raise SteamworksUnavailableError(
                "Steamworks did not provide the required user, friends, "
                "matchmaking, and UGC interfaces."
            )

    @staticmethod
    def resolve_dll_path(explicit_path: Path | None = None) -> Path:
        candidates: list[Path] = []

        if explicit_path is not None:
            candidates.append(Path(explicit_path))

        configured_dll = os.environ.get("SAVESHIFT_STEAM_API_PATH")

        if configured_dll:
            candidates.append(Path(configured_dll))

        configured_sdk = os.environ.get("STEAMWORKS_SDK_PATH")

        if configured_sdk:
            candidates.append(
                Path(configured_sdk)
                / "redistributable_bin"
                / "win64"
                / "steam_api64.dll"
            )

        executable_directory = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                executable_directory / "steam_api64.dll",
                executable_directory / "_internal" / "steam_api64.dll",
                Path.home()
                / "sdk"
                / "redistributable_bin"
                / "win64"
                / "steam_api64.dll",
            ]
        )

        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()

        raise SteamworksUnavailableError(
            "steam_api64.dll was not found. Install Save Shift through Steam or "
            "set STEAMWORKS_SDK_PATH for local development."
        )

    def publish_item(
        self,
        content_directory: Path,
        *,
        title: str,
        description: str,
        metadata: str,
        visibility: SteamUgcVisibility,
    ) -> SteamPublishedItem:
        content_directory = content_directory.resolve()

        if not content_directory.is_dir():
            raise FileNotFoundError(
                f"Steam UGC content directory does not exist: {content_directory}"
            )

        with self._lock:
            self._ensure_open()
            create_call = self._api.SteamAPI_ISteamUGC_CreateItem(
                self._ugc,
                SAVESHIFT_STEAM_APP_ID,
                _WORKSHOP_FILE_TYPE_COMMUNITY,
            )
            create_result = self._await_call(
                create_call,
                _CreateItemResult,
                _CREATE_ITEM_CALLBACK,
            )
            self._require_ok("create Workshop item", create_result.result)
            published_file_id = int(create_result.published_file_id)

            if published_file_id < 1:
                raise SteamworksError(
                    "Steam created an invalid Workshop item identifier."
                )

            try:
                update_handle = self._api.SteamAPI_ISteamUGC_StartItemUpdate(
                    self._ugc,
                    SAVESHIFT_STEAM_APP_ID,
                    published_file_id,
                )

                if update_handle == _INVALID_UPDATE_HANDLE:
                    raise SteamworksError(
                        "Steam could not start the Workshop item upload."
                    )

                self._require_true(
                    "set Workshop title",
                    self._api.SteamAPI_ISteamUGC_SetItemTitle(
                        self._ugc,
                        update_handle,
                        title.encode("utf-8"),
                    ),
                )
                self._require_true(
                    "set Workshop description",
                    self._api.SteamAPI_ISteamUGC_SetItemDescription(
                        self._ugc,
                        update_handle,
                        description.encode("utf-8"),
                    ),
                )
                self._require_true(
                    "set Workshop metadata",
                    self._api.SteamAPI_ISteamUGC_SetItemMetadata(
                        self._ugc,
                        update_handle,
                        metadata.encode("utf-8"),
                    ),
                )
                self._require_true(
                    "set Workshop visibility",
                    self._api.SteamAPI_ISteamUGC_SetItemVisibility(
                        self._ugc,
                        update_handle,
                        int(visibility),
                    ),
                )
                self._require_true(
                    "set Workshop content",
                    self._api.SteamAPI_ISteamUGC_SetItemContent(
                        self._ugc,
                        update_handle,
                        str(content_directory).encode("utf-8"),
                    ),
                )
                submit_call = self._api.SteamAPI_ISteamUGC_SubmitItemUpdate(
                    self._ugc,
                    update_handle,
                    b"Save Shift package upload",
                )
                submit_result = self._await_call(
                    submit_call,
                    _SubmitItemUpdateResult,
                    _SUBMIT_ITEM_UPDATE_CALLBACK,
                )
                self._require_ok("upload Workshop item", submit_result.result)

                if int(submit_result.published_file_id) != published_file_id:
                    raise SteamworksError(
                        "Steam returned a different item after the upload."
                    )
            except Exception:
                self._delete_after_failed_publish(published_file_id)
                raise

            return SteamPublishedItem(
                published_file_id=str(published_file_id),
                user_needs_legal_agreement=bool(
                    create_result.needs_legal_agreement
                    or submit_result.needs_legal_agreement
                ),
            )

    def update_item(
        self,
        published_file_id: str,
        content_directory: Path,
        *,
        title: str,
        description: str,
        metadata: str,
        visibility: SteamUgcVisibility,
    ) -> SteamPublishedItem:
        numeric_id = self._parse_published_file_id(published_file_id)
        content_directory = content_directory.resolve()
        if not content_directory.is_dir():
            raise FileNotFoundError(
                f"Steam UGC content directory does not exist: {content_directory}"
            )
        with self._lock:
            self._ensure_open()
            update_handle = self._api.SteamAPI_ISteamUGC_StartItemUpdate(
                self._ugc,
                SAVESHIFT_STEAM_APP_ID,
                numeric_id,
            )
            if update_handle == _INVALID_UPDATE_HANDLE:
                raise SteamworksError("Steam could not start the Workshop item update.")
            self._require_true(
                "set Workshop title",
                self._api.SteamAPI_ISteamUGC_SetItemTitle(
                    self._ugc, update_handle, title.encode("utf-8")
                ),
            )
            self._require_true(
                "set Workshop description",
                self._api.SteamAPI_ISteamUGC_SetItemDescription(
                    self._ugc, update_handle, description.encode("utf-8")
                ),
            )
            self._require_true(
                "set Workshop metadata",
                self._api.SteamAPI_ISteamUGC_SetItemMetadata(
                    self._ugc, update_handle, metadata.encode("utf-8")
                ),
            )
            self._require_true(
                "set Workshop visibility",
                self._api.SteamAPI_ISteamUGC_SetItemVisibility(
                    self._ugc, update_handle, int(visibility)
                ),
            )
            self._require_true(
                "set Workshop content",
                self._api.SteamAPI_ISteamUGC_SetItemContent(
                    self._ugc,
                    update_handle,
                    str(content_directory).encode("utf-8"),
                ),
            )
            result = self._await_call(
                self._api.SteamAPI_ISteamUGC_SubmitItemUpdate(
                    self._ugc,
                    update_handle,
                    b"Save Shift group manifest update",
                ),
                _SubmitItemUpdateResult,
                _SUBMIT_ITEM_UPDATE_CALLBACK,
            )
            self._require_ok("update Workshop item", result.result)
            if int(result.published_file_id) != numeric_id:
                raise SteamworksError(
                    "Steam returned a different item after the update."
                )
            return SteamPublishedItem(
                published_file_id=str(numeric_id),
                user_needs_legal_agreement=bool(result.needs_legal_agreement),
            )

    @diagnostic_operation("steam.download")
    def download_item(self, published_file_id: str) -> Path:
        numeric_id = self._parse_published_file_id(published_file_id)

        with self._lock:
            self._ensure_open()
            started = self._api.SteamAPI_ISteamUGC_DownloadItem(
                self._ugc,
                numeric_id,
                True,
            )
            self._require_true("start Workshop download", started)
            self._await_download(numeric_id)
            size_on_disk = ctypes.c_uint64()
            folder = ctypes.create_string_buffer(32768)
            timestamp = ctypes.c_uint32()
            installed = self._api.SteamAPI_ISteamUGC_GetItemInstallInfo(
                self._ugc,
                numeric_id,
                ctypes.byref(size_on_disk),
                folder,
                len(folder),
                ctypes.byref(timestamp),
            )
            self._require_true("locate downloaded Workshop item", installed)
            installed_path = Path(
                folder.value.decode("utf-8", errors="strict")
            )

            if not installed_path.is_dir():
                raise SteamworksError(
                    "Steam reported a Workshop directory that does not exist."
                )

            return installed_path

    def delete_item(self, published_file_id: str) -> None:
        numeric_id = self._parse_published_file_id(published_file_id)

        with self._lock:
            self._ensure_open()
            delete_call = self._api.SteamAPI_ISteamUGC_DeleteItem(
                self._ugc,
                numeric_id,
            )
            result = self._await_call(
                delete_call,
                _DeleteItemResult,
                _DELETE_ITEM_CALLBACK,
            )
            self._require_ok("delete Workshop item", result.result)

            if int(result.published_file_id) != numeric_id:
                raise SteamworksError(
                    "Steam confirmed deletion for a different Workshop item."
                )

    def current_identity(self) -> SteamIdentity:
        with self._lock:
            self._ensure_open()
            steam_id = int(self._api.SteamAPI_ISteamUser_GetSteamID(self._user))
            if steam_id < 1:
                raise SteamworksUnavailableError(
                    "Steam is not signed in to a valid account."
                )
            return SteamIdentity(
                steam_id=str(steam_id),
                persona_name=self._decode_steam_text(
                    self._api.SteamAPI_ISteamFriends_GetPersonaName(self._friends)
                ),
            )

    def list_friends(self) -> list[SteamFriend]:
        with self._lock:
            self._ensure_open()
            count = int(
                self._api.SteamAPI_ISteamFriends_GetFriendCount(
                    self._friends,
                    _FRIEND_FLAG_IMMEDIATE,
                )
            )
            if count < 0:
                raise SteamworksError("Steam could not load the friends list.")
            friends: list[SteamFriend] = []
            for index in range(count):
                steam_id = int(
                    self._api.SteamAPI_ISteamFriends_GetFriendByIndex(
                        self._friends,
                        index,
                        _FRIEND_FLAG_IMMEDIATE,
                    )
                )
                if steam_id < 1:
                    continue
                friends.append(
                    SteamFriend(
                        steam_id=str(steam_id),
                        persona_name=self._decode_steam_text(
                            self._api.SteamAPI_ISteamFriends_GetFriendPersonaName(
                                self._friends,
                                steam_id,
                            )
                        ),
                    )
                )
            return friends

    def create_private_lobby(
        self,
        *,
        maximum_members: int = 16,
        metadata: Mapping[str, str] | None = None,
    ) -> SteamLobby:
        if not 2 <= maximum_members <= 250:
            raise ValueError("A Steam lobby must allow between 2 and 250 members.")
        with self._lock:
            self._ensure_open()
            result = self._await_call(
                self._api.SteamAPI_ISteamMatchmaking_CreateLobby(
                    self._matchmaking,
                    _LOBBY_TYPE_PRIVATE,
                    maximum_members,
                ),
                _LobbyCreatedResult,
                _LOBBY_CREATED_CALLBACK,
            )
            self._require_ok("create private lobby", result.result)
            lobby = SteamLobby(lobby_id=str(int(result.lobby_id)))
            if lobby.lobby_id == "0":
                raise SteamworksError("Steam created an invalid lobby identifier.")
            for key, value in (metadata or {}).items():
                self.set_lobby_data(lobby.lobby_id, key, value)
            return lobby

    def join_lobby(self, lobby_id: str) -> SteamLobby:
        numeric_id = self._parse_steam_id(lobby_id, "lobby")
        with self._lock:
            self._ensure_open()
            result = self._await_call(
                self._api.SteamAPI_ISteamMatchmaking_JoinLobby(
                    self._matchmaking,
                    numeric_id,
                ),
                _LobbyEnterResult,
                _LOBBY_ENTER_CALLBACK,
            )
            response = int(result.chat_room_enter_response)
            if response != _CHAT_ROOM_ENTER_SUCCESS:
                raise SteamworksError(
                    "Steam did not allow this account to join the lobby "
                    f"(response {response})."
                )
            joined_id = int(result.lobby_id)
            if joined_id != numeric_id:
                raise SteamworksError("Steam joined a different lobby.")
            return SteamLobby(lobby_id=str(joined_id))

    def leave_lobby(self, lobby_id: str) -> None:
        with self._lock:
            self._ensure_open()
            self._api.SteamAPI_ISteamMatchmaking_LeaveLobby(
                self._matchmaking,
                self._parse_steam_id(lobby_id, "lobby"),
            )

    def invite_friend(self, lobby_id: str, friend_steam_id: str) -> None:
        with self._lock:
            self._ensure_open()
            invited = self._api.SteamAPI_ISteamMatchmaking_InviteUserToLobby(
                self._matchmaking,
                self._parse_steam_id(lobby_id, "lobby"),
                self._parse_steam_id(friend_steam_id, "friend"),
            )
            self._require_true("invite Steam friend to lobby", invited)

    def open_invite_overlay(self, lobby_id: str) -> None:
        with self._lock:
            self._ensure_open()
            self._api.SteamAPI_ISteamFriends_ActivateGameOverlayInviteDialog(
                self._friends,
                self._parse_steam_id(lobby_id, "lobby"),
            )

    def lobby_members(self, lobby_id: str) -> list[str]:
        numeric_id = self._parse_steam_id(lobby_id, "lobby")
        with self._lock:
            self._ensure_open()
            count = max(
                0,
                int(
                    self._api.SteamAPI_ISteamMatchmaking_GetNumLobbyMembers(
                        self._matchmaking,
                        numeric_id,
                    )
                ),
            )
            return [
                str(
                    int(
                        self._api.SteamAPI_ISteamMatchmaking_GetLobbyMemberByIndex(
                            self._matchmaking,
                            numeric_id,
                            index,
                        )
                    )
                )
                for index in range(count)
            ]

    def lobby_data(self, lobby_id: str, key: str) -> str:
        encoded_key = self._lobby_text(key, "Lobby metadata key")
        with self._lock:
            self._ensure_open()
            return self._decode_steam_text(
                self._api.SteamAPI_ISteamMatchmaking_GetLobbyData(
                    self._matchmaking,
                    self._parse_steam_id(lobby_id, "lobby"),
                    encoded_key,
                )
            )

    def set_lobby_data(self, lobby_id: str, key: str, value: str) -> None:
        encoded_key = self._lobby_text(key, "Lobby metadata key")
        encoded_value = self._lobby_text(value, "Lobby metadata value", empty=True)
        with self._lock:
            self._ensure_open()
            saved = self._api.SteamAPI_ISteamMatchmaking_SetLobbyData(
                self._matchmaking,
                self._parse_steam_id(lobby_id, "lobby"),
                encoded_key,
                encoded_value,
            )
            self._require_true("set lobby metadata", saved)

    def lobby_owner(self, lobby_id: str) -> str:
        with self._lock:
            self._ensure_open()
            owner = int(
                self._api.SteamAPI_ISteamMatchmaking_GetLobbyOwner(
                    self._matchmaking,
                    self._parse_steam_id(lobby_id, "lobby"),
                )
            )
            if owner < 1:
                raise SteamworksError("Steam returned an invalid lobby owner.")
            return str(owner)

    def send_lobby_message(self, lobby_id: str, payload: bytes) -> None:
        if not isinstance(payload, bytes) or not payload:
            raise ValueError("A Steam lobby message cannot be empty.")
        if len(payload) > _MAX_LOBBY_MESSAGE_BYTES:
            raise ValueError("A Steam lobby message cannot exceed 4000 bytes.")
        buffer = ctypes.create_string_buffer(payload, len(payload))
        with self._lock:
            self._ensure_open()
            sent = self._api.SteamAPI_ISteamMatchmaking_SendLobbyChatMsg(
                self._matchmaking,
                self._parse_steam_id(lobby_id, "lobby"),
                buffer,
                len(payload),
            )
            self._require_true("send lobby invitation data", sent)

    def poll_social_events(self) -> list[SteamSocialEvent]:
        with self._lock:
            self._ensure_open()
            events: list[SteamSocialEvent] = []
            callbacks = self._pending_social_callbacks + self._next_callbacks()
            self._pending_social_callbacks = []
            for message in callbacks:
                if message.callback_id == _GAME_LOBBY_JOIN_REQUESTED_CALLBACK:
                    request = ctypes.cast(
                        message.parameter,
                        ctypes.POINTER(_GameLobbyJoinRequested),
                    ).contents
                    events.append(
                        SteamLobbyJoinRequest(
                            lobby_id=str(int(request.lobby_id)),
                            friend_steam_id=str(int(request.friend_steam_id)),
                        )
                    )
                elif message.callback_id == _LOBBY_CHAT_MESSAGE_CALLBACK:
                    notice = ctypes.cast(
                        message.parameter,
                        ctypes.POINTER(_LobbyChatMessage),
                    ).contents
                    if int(notice.chat_entry_type) != _CHAT_ENTRY_TYPE_MESSAGE:
                        continue
                    sender = ctypes.c_uint64()
                    entry_type = ctypes.c_int()
                    payload = ctypes.create_string_buffer(
                        _MAX_LOBBY_MESSAGE_BYTES
                    )
                    size = int(
                        self._api.SteamAPI_ISteamMatchmaking_GetLobbyChatEntry(
                            self._matchmaking,
                            int(notice.lobby_id),
                            int(notice.chat_id),
                            ctypes.byref(sender),
                            payload,
                            len(payload),
                            ctypes.byref(entry_type),
                        )
                    )
                    if size > 0 and entry_type.value == _CHAT_ENTRY_TYPE_MESSAGE:
                        events.append(
                            SteamLobbyMessage(
                                lobby_id=str(int(notice.lobby_id)),
                                sender_steam_id=str(sender.value),
                                payload=bytes(payload.raw[:size]),
                            )
                        )
            return events

    def _preserve_social_callback(self, message: _CallbackMessage) -> None:
        if message.callback_id in {
            _GAME_LOBBY_JOIN_REQUESTED_CALLBACK,
            _LOBBY_CHAT_MESSAGE_CALLBACK,
        }:
            self._pending_social_callbacks.append(message)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._api.SteamAPI_Shutdown()

    def __enter__(self) -> "SteamworksUgcClient":
        self._ensure_open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _await_call(
        self,
        api_call: int,
        result_type: type[ctypes.Structure],
        expected_callback: int,
    ) -> ctypes.Structure:
        if not api_call:
            raise SteamworksError("Steam did not start the requested operation.")

        deadline = time.monotonic() + self.timeout_seconds

        while time.monotonic() < deadline:
            for message in self._next_callbacks():
                if message.callback_id != _STEAM_API_CALL_COMPLETED_CALLBACK:
                    self._preserve_social_callback(message)
                    continue

                completed = ctypes.cast(
                    message.parameter,
                    ctypes.POINTER(_ApiCallCompleted),
                ).contents

                if int(completed.api_call) != int(api_call):
                    continue

                result = result_type()
                failed = ctypes.c_bool()
                received = self._api.SteamAPI_ManualDispatch_GetAPICallResult(
                    self._pipe,
                    api_call,
                    ctypes.byref(result),
                    ctypes.sizeof(result),
                    expected_callback,
                    ctypes.byref(failed),
                )

                if not received or failed.value:
                    raise SteamworksError(
                        "Steam failed while retrieving an asynchronous result."
                    )

                return result

            time.sleep(0.02)

        raise SteamworksError("The Steam operation timed out.")

    def _await_download(self, published_file_id: int) -> None:
        started = time.monotonic()
        deadline = started + self.download_timeout_seconds
        next_diagnostic = started
        next_state_check = 0.0
        next_retry = float("inf")
        last_transient_result: int | None = None

        while time.monotonic() < deadline:
            now = time.monotonic()

            if now >= next_diagnostic:
                state = int(self._api.SteamAPI_ISteamUGC_GetItemState(
                    self._ugc, published_file_id,
                ))
                logger.info(
                    "steam.download waiting item=%d elapsed=%.1fs timeout=%.1fs state=%d",
                    published_file_id, now - started, self.download_timeout_seconds, state,
                )
                next_diagnostic = now + 15.0

            if now >= next_state_check:
                if self._item_download_ready(published_file_id):
                    return

                next_state_check = now + 0.25

            for message in self._next_callbacks():
                if message.callback_id != _DOWNLOAD_ITEM_CALLBACK:
                    self._preserve_social_callback(message)
                    continue

                result = ctypes.cast(
                    message.parameter,
                    ctypes.POINTER(_DownloadItemResult),
                ).contents

                if (
                    int(result.app_id) != SAVESHIFT_STEAM_APP_ID
                    or int(result.published_file_id) != published_file_id
                ):
                    continue

                result_code = int(result.result)
                logger.info("steam.download callback item=%d result=%d",
                            published_file_id, result_code)

                if result_code == _RESULT_OK:
                    return

                if result_code not in _TRANSIENT_DOWNLOAD_RESULTS:
                    self._require_ok("download Workshop item", result_code)

                last_transient_result = result_code
                next_retry = min(next_retry, time.monotonic() + 2.0)

            if time.monotonic() >= next_retry:
                logger.warning("steam.download retry item=%d last_result=%s",
                               published_file_id, last_transient_result)
                self._api.SteamAPI_ISteamUGC_DownloadItem(
                    self._ugc,
                    published_file_id,
                    True,
                )
                next_retry = time.monotonic() + 5.0

            time.sleep(0.02)

        logger.error("steam.download timeout item=%d last_result=%s",
                     published_file_id, last_transient_result)
        if last_transient_result is not None:
            detail = _RESULT_MESSAGES.get(
                last_transient_result,
                "unknown Steam error",
            )
            raise SteamworksError(
                "The Steam Workshop download did not recover before timing "
                f"out (last result: EResult {last_transient_result}, {detail})."
            )

        raise SteamworksError("The Steam Workshop download timed out.")

    def _item_download_ready(self, published_file_id: int) -> bool:
        state = int(
            self._api.SteamAPI_ISteamUGC_GetItemState(
                self._ugc,
                published_file_id,
            )
        )
        unavailable_states = (
            _ITEM_STATE_NEEDS_UPDATE
            | _ITEM_STATE_DOWNLOADING
            | _ITEM_STATE_DOWNLOAD_PENDING
        )
        return bool(state & _ITEM_STATE_INSTALLED) and not bool(
            state & unavailable_states
        )

    def _next_callbacks(self) -> list[_CallbackMessage]:
        self._api.SteamAPI_ManualDispatch_RunFrame(self._pipe)
        callbacks: list[_CallbackMessage] = []

        while True:
            message = _CallbackMessage()

            if not self._api.SteamAPI_ManualDispatch_GetNextCallback(
                self._pipe,
                ctypes.byref(message),
            ):
                break

            try:
                parameter_copy = (ctypes.c_uint8 * message.parameter_size)()
                ctypes.memmove(
                    parameter_copy,
                    message.parameter,
                    message.parameter_size,
                )
                callbacks.append(
                    _CallbackMessage(
                        steam_user=message.steam_user,
                        callback_id=message.callback_id,
                        parameter=ctypes.cast(
                            parameter_copy,
                            ctypes.POINTER(ctypes.c_uint8),
                        ),
                        parameter_size=message.parameter_size,
                    )
                )
                callbacks[-1]._parameter_copy = parameter_copy
            finally:
                self._api.SteamAPI_ManualDispatch_FreeLastCallback(self._pipe)

        return callbacks

    def _delete_after_failed_publish(self, published_file_id: int) -> None:
        try:
            self.delete_item(str(published_file_id))
        except Exception as error:
            logger.warning(
                "Could not remove incomplete Steam Workshop item %s: %s",
                published_file_id,
                error,
            )

    def _configure_signatures(self) -> None:
        signatures = {
            "SteamAPI_InitFlat": ([ctypes.c_void_p], ctypes.c_int),
            "SteamAPI_Shutdown": ([], None),
            "SteamAPI_GetHSteamPipe": ([], ctypes.c_int32),
            "SteamAPI_ManualDispatch_Init": ([], None),
            "SteamAPI_ManualDispatch_RunFrame": ([ctypes.c_int32], None),
            "SteamAPI_ManualDispatch_GetNextCallback": (
                [ctypes.c_int32, ctypes.POINTER(_CallbackMessage)],
                ctypes.c_bool,
            ),
            "SteamAPI_ManualDispatch_FreeLastCallback": ([ctypes.c_int32], None),
            "SteamAPI_ManualDispatch_GetAPICallResult": (
                [
                    ctypes.c_int32,
                    ctypes.c_uint64,
                    ctypes.c_void_p,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.POINTER(ctypes.c_bool),
                ],
                ctypes.c_bool,
            ),
            "SteamAPI_SteamUGC_v021": ([], ctypes.c_void_p),
            "SteamAPI_SteamUser_v023": ([], ctypes.c_void_p),
            "SteamAPI_SteamFriends_v018": ([], ctypes.c_void_p),
            "SteamAPI_SteamMatchmaking_v009": ([], ctypes.c_void_p),
            "SteamAPI_ISteamUser_GetSteamID": (
                [ctypes.c_void_p],
                ctypes.c_uint64,
            ),
            "SteamAPI_ISteamFriends_GetPersonaName": (
                [ctypes.c_void_p],
                ctypes.c_char_p,
            ),
            "SteamAPI_ISteamFriends_GetFriendCount": (
                [ctypes.c_void_p, ctypes.c_int],
                ctypes.c_int,
            ),
            "SteamAPI_ISteamFriends_GetFriendByIndex": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.c_int],
                ctypes.c_uint64,
            ),
            "SteamAPI_ISteamFriends_GetFriendPersonaName": (
                [ctypes.c_void_p, ctypes.c_uint64],
                ctypes.c_char_p,
            ),
            "SteamAPI_ISteamFriends_ActivateGameOverlayInviteDialog": (
                [ctypes.c_void_p, ctypes.c_uint64],
                None,
            ),
            "SteamAPI_ISteamMatchmaking_CreateLobby": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.c_int],
                ctypes.c_uint64,
            ),
            "SteamAPI_ISteamMatchmaking_JoinLobby": (
                [ctypes.c_void_p, ctypes.c_uint64],
                ctypes.c_uint64,
            ),
            "SteamAPI_ISteamMatchmaking_LeaveLobby": (
                [ctypes.c_void_p, ctypes.c_uint64],
                None,
            ),
            "SteamAPI_ISteamMatchmaking_InviteUserToLobby": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64],
                ctypes.c_bool,
            ),
            "SteamAPI_ISteamMatchmaking_GetNumLobbyMembers": (
                [ctypes.c_void_p, ctypes.c_uint64],
                ctypes.c_int,
            ),
            "SteamAPI_ISteamMatchmaking_GetLobbyMemberByIndex": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_int],
                ctypes.c_uint64,
            ),
            "SteamAPI_ISteamMatchmaking_GetLobbyData": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_char_p],
                ctypes.c_char_p,
            ),
            "SteamAPI_ISteamMatchmaking_SetLobbyData": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_char_p, ctypes.c_char_p],
                ctypes.c_bool,
            ),
            "SteamAPI_ISteamMatchmaking_GetLobbyOwner": (
                [ctypes.c_void_p, ctypes.c_uint64],
                ctypes.c_uint64,
            ),
            "SteamAPI_ISteamMatchmaking_SendLobbyChatMsg": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int],
                ctypes.c_bool,
            ),
            "SteamAPI_ISteamMatchmaking_GetLobbyChatEntry": (
                [
                    ctypes.c_void_p,
                    ctypes.c_uint64,
                    ctypes.c_int,
                    ctypes.POINTER(ctypes.c_uint64),
                    ctypes.c_void_p,
                    ctypes.c_int,
                    ctypes.POINTER(ctypes.c_int),
                ],
                ctypes.c_int,
            ),
            "SteamAPI_ISteamUGC_CreateItem": (
                [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int],
                ctypes.c_uint64,
            ),
            "SteamAPI_ISteamUGC_StartItemUpdate": (
                [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint64],
                ctypes.c_uint64,
            ),
            "SteamAPI_ISteamUGC_SetItemTitle": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_char_p],
                ctypes.c_bool,
            ),
            "SteamAPI_ISteamUGC_SetItemDescription": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_char_p],
                ctypes.c_bool,
            ),
            "SteamAPI_ISteamUGC_SetItemMetadata": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_char_p],
                ctypes.c_bool,
            ),
            "SteamAPI_ISteamUGC_SetItemVisibility": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_int],
                ctypes.c_bool,
            ),
            "SteamAPI_ISteamUGC_SetItemContent": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_char_p],
                ctypes.c_bool,
            ),
            "SteamAPI_ISteamUGC_SubmitItemUpdate": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_char_p],
                ctypes.c_uint64,
            ),
            "SteamAPI_ISteamUGC_DownloadItem": (
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_bool],
                ctypes.c_bool,
            ),
            "SteamAPI_ISteamUGC_GetItemState": (
                [ctypes.c_void_p, ctypes.c_uint64],
                ctypes.c_uint32,
            ),
            "SteamAPI_ISteamUGC_GetItemInstallInfo": (
                [
                    ctypes.c_void_p,
                    ctypes.c_uint64,
                    ctypes.POINTER(ctypes.c_uint64),
                    ctypes.c_void_p,
                    ctypes.c_uint32,
                    ctypes.POINTER(ctypes.c_uint32),
                ],
                ctypes.c_bool,
            ),
            "SteamAPI_ISteamUGC_DeleteItem": (
                [ctypes.c_void_p, ctypes.c_uint64],
                ctypes.c_uint64,
            ),
        }

        for function_name, (argument_types, return_type) in signatures.items():
            function = getattr(self._api, function_name, None)

            if function is None:
                raise SteamworksUnavailableError(
                    f"The Steamworks SDK is missing {function_name}."
                )

            function.argtypes = argument_types
            function.restype = return_type

    def _ensure_open(self) -> None:
        if self._closed:
            raise SteamworksError("The Steamworks client is closed.")

    @staticmethod
    def _parse_published_file_id(value: str) -> int:
        normalized = str(value).strip()

        if not normalized.isdigit() or int(normalized) < 1:
            raise SteamworksError("The Workshop item identifier is invalid.")

        return int(normalized)

    @staticmethod
    def _parse_steam_id(value: str, label: str) -> int:
        normalized = str(value).strip()
        if not normalized.isdigit() or int(normalized) < 1:
            raise ValueError(f"The Steam {label} identifier is invalid.")
        return int(normalized)

    @staticmethod
    def _decode_steam_text(value: bytes | None) -> str:
        return value.decode("utf-8", errors="replace") if value else ""

    @staticmethod
    def _lobby_text(value: str, label: str, *, empty: bool = False) -> bytes:
        if not isinstance(value, str) or (not empty and not value):
            raise ValueError(f"{label} cannot be empty.")
        if "\x00" in value:
            raise ValueError(f"{label} cannot contain a null character.")
        return value.encode("utf-8")

    @staticmethod
    def _require_true(operation: str, succeeded: bool) -> None:
        if not succeeded:
            raise SteamworksError(f"Steam could not {operation}.")

    @staticmethod
    def _require_ok(operation: str, result: int) -> None:
        if result != _RESULT_OK:
            detail = _RESULT_MESSAGES.get(result, "unknown Steam error")
            raise SteamworksError(
                f"Steam could not {operation} (EResult {result}: {detail})."
            )
