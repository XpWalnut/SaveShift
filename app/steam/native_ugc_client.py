import ctypes
import os
import sys
import threading
import time
from pathlib import Path

from app.core.logging import diagnostic_operation, logger
from app.steam.constants import SAVESHIFT_STEAM_APP_ID
from app.steam.errors import SteamworksError, SteamworksUnavailableError
from app.steam.ugc_client import (
    SteamPublishedItem,
    SteamUgcVisibility,
)


_RESULT_OK = 1
_WORKSHOP_FILE_TYPE_COMMUNITY = 0
_INVALID_UPDATE_HANDLE = 0xFFFFFFFFFFFFFFFF
_STEAM_API_CALL_COMPLETED_CALLBACK = 703
_CREATE_ITEM_CALLBACK = 3403
_SUBMIT_ITEM_UPDATE_CALLBACK = 3404
_DOWNLOAD_ITEM_CALLBACK = 3406
_DELETE_ITEM_CALLBACK = 3417
_ITEM_STATE_INSTALLED = 4
_ITEM_STATE_NEEDS_UPDATE = 8
_ITEM_STATE_DOWNLOADING = 16
_ITEM_STATE_DOWNLOAD_PENDING = 32
_TRANSIENT_DOWNLOAD_RESULTS = {2, 3, 16, 20, 50, 53}

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

        if self._pipe == 0 or not self._ugc:
            self.close()
            raise SteamworksUnavailableError(
                "Steamworks did not provide the current user UGC interface."
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
