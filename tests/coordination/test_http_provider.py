from datetime import UTC, datetime
from io import BytesIO
import json
from urllib.error import HTTPError, URLError

import pytest

from app.coordination.errors import (
    CoordinationConfigurationError,
    CoordinationUnavailableError,
    LockConflictError,
    LockOwnershipError,
)
from app.coordination.http_provider import HttpCoordinationProvider
from app.coordination.models import LockLease


PROJECT_UUID = "12345678-1234-5678-1234-567812345678"


def _lock_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "project_uuid": PROJECT_UUID,
        "lease_id": "lease-123",
        "fencing_token": 7,
        "owner_device_id": "device-123",
        "owner_display_name": "Jake",
        "acquired_at_utc": "2026-07-13T20:00:00Z",
        "expires_at_utc": "2026-07-13T20:15:00+00:00",
    }
    data.update(overrides)
    return data


class _Response:
    def __init__(self, data: dict[str, object]) -> None:
        self._body = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def read(self) -> bytes:
        return self._body


def test_pair_uses_versioned_contract_and_returns_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = []

    def fake_urlopen(request, timeout: float):
        requests.append((request, timeout))
        return _Response(
            {
                "device": {
                    "device_id": "device-123",
                    "device_token": "secret-token",
                }
            }
        )

    monkeypatch.setattr("app.coordination.http_provider.urlopen", fake_urlopen)
    provider = HttpCoordinationProvider("https://locks.example.com/")

    device = provider.pair("  pair-code  ", "  Gaming PC  ")

    request, timeout = requests[0]
    assert request.full_url == "https://locks.example.com/api/v1/devices/pair"
    assert request.method == "POST"
    assert request.get_header("Authorization") is None
    assert json.loads(request.data) == {
        "pairing_code": "pair-code",
        "device_name": "Gaming PC",
    }
    assert timeout == 5.0
    assert device.device_id == "device-123"
    assert device.device_token == "secret-token"


def test_acquire_renew_status_and_release_use_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = []
    responses = [
        {"lock": _lock_data()},
        {"lock": _lock_data(expires_at_utc="2026-07-13T20:20:00Z")},
        {"lock": _lock_data()},
        {},
    ]

    def fake_urlopen(request, timeout: float):
        requests.append(request)
        return _Response(responses.pop(0))

    monkeypatch.setattr("app.coordination.http_provider.urlopen", fake_urlopen)
    provider = HttpCoordinationProvider(
        "https://locks.example.com",
        device_token="device-token",
    )

    acquired = provider.acquire_lock(PROJECT_UUID, "Jake")
    renewed = provider.renew_lock(acquired)
    status = provider.get_lock(PROJECT_UUID)
    provider.release_lock(renewed)

    assert acquired.fencing_token == 7
    assert acquired.acquired_at_utc == datetime(2026, 7, 13, 20, tzinfo=UTC)
    assert renewed.expires_at_utc == datetime(2026, 7, 13, 20, 20, tzinfo=UTC)
    assert status == acquired
    assert [request.method for request in requests] == ["POST", "POST", "GET", "POST"]
    assert all(
        request.get_header("Authorization") == "Bearer device-token"
        for request in requests
    )
    assert requests[0].full_url.endswith(f"/locks/{PROJECT_UUID}/acquire")
    assert requests[1].full_url.endswith(f"/locks/{PROJECT_UUID}/renew")
    assert requests[2].full_url.endswith(f"/locks/{PROJECT_UUID}")
    assert requests[3].full_url.endswith(f"/locks/{PROJECT_UUID}/release")


def test_status_returns_none_when_project_is_unlocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.coordination.http_provider.urlopen",
        lambda *_args, **_kwargs: _Response({"lock": None}),
    )
    provider = HttpCoordinationProvider(
        "https://locks.example.com",
        device_token="device-token",
    )

    assert provider.get_lock(PROJECT_UUID) is None


def test_conflict_response_preserves_current_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps(
        {
            "error": {
                "code": "lock_conflict",
                "message": "Project is hosted by Alex.",
                "lock": _lock_data(owner_display_name="Alex"),
            }
        }
    ).encode("utf-8")

    def raise_conflict(*_args, **_kwargs):
        raise HTTPError(
            url="https://locks.example.com",
            code=409,
            msg="Conflict",
            hdrs=None,
            fp=BytesIO(body),
        )

    monkeypatch.setattr("app.coordination.http_provider.urlopen", raise_conflict)
    provider = HttpCoordinationProvider(
        "https://locks.example.com",
        device_token="device-token",
    )

    with pytest.raises(LockConflictError, match="hosted by Alex") as captured:
        provider.acquire_lock(PROJECT_UUID, "Jake")

    assert captured.value.lock.owner_display_name == "Alex"


def test_expired_lease_is_reported_as_lost_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"error":{"code":"lease_expired","message":"Lease expired."}}'

    def raise_expired(*_args, **_kwargs):
        raise HTTPError(
            url="https://locks.example.com",
            code=409,
            msg="Conflict",
            hdrs=None,
            fp=BytesIO(body),
        )

    monkeypatch.setattr("app.coordination.http_provider.urlopen", raise_expired)
    provider = HttpCoordinationProvider(
        "https://locks.example.com",
        device_token="device-token",
    )

    with pytest.raises(LockOwnershipError, match="Lease expired"):
        provider.renew_lock(LockLease.from_dict(_lock_data()))


@pytest.mark.parametrize("status_code", [401, 403])
def test_authentication_errors_are_not_reported_as_availability_failures(
    status_code: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_auth_error(*_args, **_kwargs):
        raise HTTPError(
            url="https://locks.example.com",
            code=status_code,
            msg="Unauthorized",
            hdrs=None,
            fp=BytesIO(b'{"error":{"message":"Pair this device again."}}'),
        )

    monkeypatch.setattr("app.coordination.http_provider.urlopen", raise_auth_error)
    provider = HttpCoordinationProvider(
        "https://locks.example.com",
        device_token="device-token",
    )

    with pytest.raises(LockOwnershipError, match="Pair this device again"):
        provider.get_lock(PROJECT_UUID)


def test_network_errors_are_reported_as_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_network_error(*_args, **_kwargs):
        raise URLError("offline")

    monkeypatch.setattr("app.coordination.http_provider.urlopen", raise_network_error)
    provider = HttpCoordinationProvider(
        "https://locks.example.com",
        device_token="device-token",
    )

    with pytest.raises(CoordinationUnavailableError, match="could not be reached"):
        provider.get_lock(PROJECT_UUID)


@pytest.mark.parametrize(
    "url",
    [
        "http://locks.example.com",
        "https://user:password@locks.example.com",
        "https://locks.example.com?token=secret",
        "not-a-url",
    ],
)
def test_provider_rejects_untrusted_base_urls(url: str) -> None:
    with pytest.raises(CoordinationConfigurationError):
        HttpCoordinationProvider(url)


def test_local_http_endpoint_is_allowed_for_development() -> None:
    provider = HttpCoordinationProvider("http://127.0.0.1:8787")

    assert provider.base_url == "http://127.0.0.1:8787"


def test_authenticated_operation_requires_device_token() -> None:
    provider = HttpCoordinationProvider("https://locks.example.com")

    with pytest.raises(CoordinationConfigurationError, match="not paired"):
        provider.get_lock(PROJECT_UUID)
