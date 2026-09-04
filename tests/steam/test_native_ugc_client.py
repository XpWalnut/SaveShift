import ctypes
from pathlib import Path

import pytest

from app.steam.constants import SAVESHIFT_STEAM_APP_ID
from app.steam.errors import SteamworksError, SteamworksUnavailableError
from app.steam.native_ugc_client import (
    _CREATE_ITEM_CALLBACK,
    _DELETE_ITEM_CALLBACK,
    _DOWNLOAD_ITEM_CALLBACK,
    _CallbackMessage,
    _DownloadItemResult,
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
