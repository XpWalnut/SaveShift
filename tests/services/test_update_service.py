from io import BytesIO
import hashlib
import json
from pathlib import Path

import pytest

from app.updates.models import UpdateRelease
from app.updates.service import UpdateError, UpdateService


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.close()


def _release_data(
    version: str,
    *,
    draft: bool = False,
    include_installer: bool = True,
) -> dict[str, object]:
    installer_name = f"SaveShiftSetup-{version}.exe"
    assets = []

    if include_installer:
        assets.append(
            {
                "name": installer_name,
                "browser_download_url": (
                    f"https://github.com/XpWalnut/SaveShift/releases/download/"
                    f"v{version}/{installer_name}"
                ),
                "size": 123,
                "digest": "sha256:" + "a" * 64,
            }
        )

    return {
        "tag_name": f"v{version}",
        "name": f"Save Shift {version}",
        "body": f"Release notes for {version}",
        "html_url": f"https://github.com/XpWalnut/SaveShift/releases/tag/v{version}",
        "draft": draft,
        "prerelease": "alpha" in version,
        "assets": assets,
    }


def _update_release(
    payload: bytes,
    *,
    digest: str | None = None,
    installer_url: str = (
        "https://github.com/XpWalnut/SaveShift/releases/download/"
        "v0.2.0/SaveShiftSetup-0.2.0.exe"
    ),
) -> UpdateRelease:
    return UpdateRelease(
        version="0.2.0",
        tag_name="v0.2.0",
        name="Save Shift 0.2.0",
        notes="Test release",
        installer_url=installer_url,
        installer_name="SaveShiftSetup-0.2.0.exe",
        installer_size=len(payload),
        installer_digest=digest,
        release_url="https://github.com/XpWalnut/SaveShift/releases/tag/v0.2.0",
    )


def test_check_for_update_selects_newest_published_release_with_installer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    releases = [
        _release_data("0.3.0-alpha.1", draft=True),
        _release_data("0.2.0-alpha.2"),
        _release_data("0.2.0-alpha.3", include_installer=False),
        _release_data("0.1.0-alpha.1"),
    ]
    monkeypatch.setattr(
        "app.updates.service.urlopen",
        lambda _request, timeout: FakeResponse(json.dumps(releases).encode())
        if timeout == 5
        else pytest.fail("wrong timeout"),
    )

    result = UpdateService.check_for_update(current_version="0.1.0-alpha.2")

    assert result is not None
    assert result.version == "0.2.0-alpha.2"
    assert result.installer_name == "SaveShiftSetup-0.2.0-alpha.2.exe"
    assert result.notes == "Release notes for 0.2.0-alpha.2"


def test_check_for_update_returns_none_when_no_newer_release_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    releases = [
        _release_data("0.1.0-alpha.2"),
        _release_data("0.1.0-alpha.1"),
    ]
    monkeypatch.setattr(
        "app.updates.service.urlopen",
        lambda _request, timeout: FakeResponse(json.dumps(releases).encode()),
    )

    assert UpdateService.check_for_update("0.1.0-alpha.2") is None


def test_check_for_update_rejects_unexpected_github_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.updates.service.urlopen",
        lambda _request, timeout: FakeResponse(b'{"message": "rate limited"}'),
    )

    with pytest.raises(UpdateError, match="unexpected releases response"):
        UpdateService.check_for_update()


def test_download_installer_verifies_digest_and_reports_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"verified-installer-payload"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    release = _update_release(payload, digest=digest)
    progress: list[int] = []
    monkeypatch.setattr(
        "app.updates.service.urlopen",
        lambda _request, timeout: FakeResponse(payload),
    )

    result = UpdateService.download_installer(
        release,
        progress_callback=progress.append,
        destination_directory=tmp_path / "updates",
    )

    assert result.read_bytes() == payload
    assert result.name == release.installer_name
    assert progress[-1] == 100
    assert not result.with_suffix(".exe.download").exists()


def test_download_installer_removes_partial_file_after_digest_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"tampered-installer"
    release = _update_release(payload, digest="sha256:" + "0" * 64)
    destination = tmp_path / "updates"
    monkeypatch.setattr(
        "app.updates.service.urlopen",
        lambda _request, timeout: FakeResponse(payload),
    )

    with pytest.raises(UpdateError, match="failed SHA-256 verification"):
        UpdateService.download_installer(
            release,
            destination_directory=destination,
        )

    assert list(destination.iterdir()) == []


def test_download_installer_rejects_incomplete_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"incomplete"
    release = _update_release(payload + b"expected-extra-data")
    destination = tmp_path / "updates"
    monkeypatch.setattr(
        "app.updates.service.urlopen",
        lambda _request, timeout: FakeResponse(payload),
    )

    with pytest.raises(UpdateError, match="installer size did not match"):
        UpdateService.download_installer(
            release,
            destination_directory=destination,
        )

    assert list(destination.iterdir()) == []


def test_download_installer_rejects_untrusted_url(tmp_path: Path) -> None:
    release = _update_release(
        b"payload",
        installer_url="https://example.com/SaveShiftSetup-0.2.0.exe",
    )

    with pytest.raises(UpdateError, match="not a trusted GitHub URL"):
        UpdateService.download_installer(
            release,
            destination_directory=tmp_path,
        )


def test_launch_installer_starts_downloaded_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer_path = tmp_path / "SaveShiftSetup-0.2.0.exe"
    installer_path.write_bytes(b"installer")
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "app.updates.service.subprocess.Popen",
        lambda command: calls.append(command),
    )

    UpdateService.launch_installer(installer_path)

    assert calls == [[str(installer_path)]]
