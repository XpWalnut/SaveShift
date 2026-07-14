import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from app.coordination.errors import (
    CoordinationConfigurationError,
    CoordinationUnavailableError,
    LockConflictError,
    LockOwnershipError,
)
from app.coordination.models import LockLease, PairedDevice


class HttpCoordinationProvider:
    API_PREFIX = "/api/v1"

    def __init__(
        self,
        base_url: str,
        device_token: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.base_url = self._validate_base_url(base_url)
        self.device_token = device_token.strip() if device_token else None
        self.timeout_seconds = timeout_seconds

    def pair(self, pairing_code: str, device_name: str) -> PairedDevice:
        data = self._request_json(
            method="POST",
            path=f"{self.API_PREFIX}/devices/pair",
            payload={
                "pairing_code": pairing_code.strip(),
                "device_name": device_name.strip(),
            },
            authenticated=False,
        )
        device = data.get("device")

        if not isinstance(device, dict):
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid pairing response."
            )

        device_id = device.get("device_id")
        device_token = device.get("device_token")

        if not isinstance(device_id, str) or not device_id:
            raise CoordinationUnavailableError(
                "The coordination provider did not return a device ID."
            )

        if not isinstance(device_token, str) or not device_token:
            raise CoordinationUnavailableError(
                "The coordination provider did not return a device token."
            )

        return PairedDevice(device_id=device_id, device_token=device_token)

    def acquire_lock(
        self,
        project_uuid: str,
        owner_display_name: str,
    ) -> LockLease:
        data = self._request_json(
            method="POST",
            path=self._lock_path(project_uuid, "acquire"),
            payload={"owner_display_name": owner_display_name.strip()},
        )
        return self._parse_lock(data)

    def renew_lock(self, lease: LockLease) -> LockLease:
        data = self._request_json(
            method="POST",
            path=self._lock_path(lease.project_uuid, "renew"),
            payload={"lease_id": lease.lease_id},
        )
        return self._parse_lock(data)

    def release_lock(self, lease: LockLease) -> None:
        self._request_json(
            method="POST",
            path=self._lock_path(lease.project_uuid, "release"),
            payload={"lease_id": lease.lease_id},
        )

    def get_lock(self, project_uuid: str) -> LockLease | None:
        data = self._request_json(
            method="GET",
            path=self._lock_path(project_uuid),
        )
        lock = data.get("lock")

        if lock is None:
            return None

        if not isinstance(lock, dict):
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid lock response."
            )

        return self._lock_from_dict(lock)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SaveShift-Coordination/1",
        }

        if authenticated:
            if not self.device_token:
                raise CoordinationConfigurationError(
                    "This computer is not paired with the coordination provider."
                )

            headers["Authorization"] = f"Bearer {self.device_token}"

        body = None

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_data = response.read()
        except HTTPError as error:
            self._raise_http_error(error)
        except (URLError, OSError, TimeoutError) as error:
            raise CoordinationUnavailableError(
                "The coordination provider could not be reached."
            ) from error

        try:
            parsed = json.loads(response_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CoordinationUnavailableError(
                "The coordination provider returned invalid JSON."
            ) from error

        if not isinstance(parsed, dict):
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid response."
            )

        return parsed

    def _raise_http_error(self, error: HTTPError) -> None:
        try:
            data = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {}

        error_data = data.get("error") if isinstance(data, dict) else None
        message = (
            error_data.get("message")
            if isinstance(error_data, dict)
            and isinstance(error_data.get("message"), str)
            else f"The coordination provider returned HTTP {error.code}."
        )
        error_code = (
            error_data.get("code")
            if isinstance(error_data, dict)
            and isinstance(error_data.get("code"), str)
            else None
        )

        if error.code == 409 and error_code == "lock_conflict":
            lock_data = (
                error_data.get("lock")
                if isinstance(error_data, dict)
                else None
            )
            lock = (
                self._lock_from_dict(lock_data)
                if isinstance(lock_data, dict)
                else None
            )
            raise LockConflictError(message, lock=lock) from error

        if error.code in (401, 403) or error_code in {
            "lease_expired",
            "lock_ownership_lost",
        }:
            raise LockOwnershipError(message) from error

        raise CoordinationUnavailableError(message) from error

    @staticmethod
    def _validate_base_url(base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        parsed = urlparse(normalized)
        is_local_development = (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost"}
        )

        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (parsed.scheme != "https" and not is_local_development)
        ):
            raise CoordinationConfigurationError(
                "The coordination provider URL must be HTTPS."
            )

        return normalized

    @staticmethod
    def _lock_path(project_uuid: str, action: str | None = None) -> str:
        path = f"{HttpCoordinationProvider.API_PREFIX}/locks/{quote(project_uuid, safe='')}"
        return f"{path}/{action}" if action else path

    @staticmethod
    def _lock_from_dict(data: dict[str, object]) -> LockLease:
        try:
            return LockLease.from_dict(data)
        except ValueError as error:
            raise CoordinationUnavailableError(
                "The coordination provider returned invalid lock data."
            ) from error

    @classmethod
    def _parse_lock(cls, data: dict[str, Any]) -> LockLease:
        lock = data.get("lock")

        if not isinstance(lock, dict):
            raise CoordinationUnavailableError(
                "The coordination provider did not return a lock."
            )

        return cls._lock_from_dict(lock)
