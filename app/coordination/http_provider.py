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
    PackageCatalogConflictError,
    PackageKeyRotatedError,
)
from app.coordination.models import (
    CatalogPackage,
    CoordinationDevice,
    GroupInvitation,
    GroupLeaveResult,
    LockLease,
    PackageCatalogMetadata,
    PackageEncryptionKey,
    PairedDevice,
    parse_utc_datetime,
)
from app.package_transport.models import PackageArtifact


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
        return self._parse_paired_device(data)

    def bootstrap(
        self,
        bootstrap_token: str,
        device_name: str,
    ) -> PairedDevice:
        data = self._request_json(
            method="POST",
            path=f"{self.API_PREFIX}/devices/bootstrap",
            payload={
                "bootstrap_token": bootstrap_token.strip(),
                "device_name": device_name.strip(),
            },
            authenticated=False,
        )
        return self._parse_paired_device(data)

    def join(
        self,
        invitation_token: str,
        device_name: str,
    ) -> PairedDevice:
        data = self._request_json(
            method="POST",
            path=f"{self.API_PREFIX}/devices/join",
            payload={
                "invitation_token": invitation_token.strip(),
                "device_name": device_name.strip(),
            },
            authenticated=False,
        )
        return self._parse_paired_device(data)

    def claim_administrator(self, pairing_code: str) -> None:
        data = self._request_json(
            method="POST",
            path=f"{self.API_PREFIX}/devices/claim-administrator",
            payload={"pairing_code": pairing_code.strip()},
        )

        if data.get("administrator") is not True:
            raise CoordinationUnavailableError(
                "The coordination provider did not grant administrator access."
            )

    def create_invitation(
        self,
        expires_in_seconds: int = 86400,
    ) -> GroupInvitation:
        data = self._request_json(
            method="POST",
            path=f"{self.API_PREFIX}/invitations",
            payload={"expires_in_seconds": expires_in_seconds},
        )
        invitation = data.get("invitation")

        if not isinstance(invitation, dict):
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid invitation."
            )

        token = invitation.get("invitation_token")
        expires_at = invitation.get("expires_at_utc")

        if not isinstance(token, str) or not token:
            raise CoordinationUnavailableError(
                "The coordination provider did not return an invitation token."
            )
        if not isinstance(expires_at, str):
            raise CoordinationUnavailableError(
                "The coordination provider did not return an invitation expiration."
            )

        try:
            parsed_expiration = parse_utc_datetime(expires_at)
        except ValueError as error:
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid invitation expiration."
            ) from error

        return GroupInvitation(
            provider_url=self.base_url,
            invitation_token=token,
            expires_at_utc=parsed_expiration,
        )

    def list_devices(self) -> list[CoordinationDevice]:
        data = self._request_json(
            method="GET",
            path=f"{self.API_PREFIX}/devices",
        )
        devices = data.get("devices")

        if not isinstance(devices, list):
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid device list."
            )

        parsed: list[CoordinationDevice] = []

        try:
            for device in devices:
                if not isinstance(device, dict):
                    raise ValueError("Invalid device record.")
                parsed.append(CoordinationDevice.from_dict(device))
        except ValueError as error:
            raise CoordinationUnavailableError(
                "The coordination provider returned invalid device data."
            ) from error

        return parsed

    def revoke_device(self, device_id: str) -> None:
        self._request_json(
            method="POST",
            path=(
                f"{self.API_PREFIX}/devices/"
                f"{quote(device_id.strip(), safe='')}/revoke"
            ),
            payload={},
        )

    def leave_group(self) -> GroupLeaveResult:
        data = self._request_json(
            method="POST",
            path=f"{self.API_PREFIX}/devices/leave",
            payload={},
        )
        group_empty = data.get("group_empty")

        if not isinstance(group_empty, bool):
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid leave response."
            )

        return GroupLeaveResult(group_empty=group_empty)

    def health(self) -> dict[str, Any]:
        return self._request_json(
            method="GET",
            path="/health",
            authenticated=False,
        )

    @staticmethod
    def _parse_paired_device(data: dict[str, Any]) -> PairedDevice:
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

        administrator = device.get("administrator", False)

        if not isinstance(administrator, bool):
            raise CoordinationUnavailableError(
                "The coordination provider returned invalid device access."
            )

        return PairedDevice(
            device_id=device_id,
            device_token=device_token,
            administrator=administrator,
        )

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

    def register_package(
        self,
        artifact: PackageArtifact,
        lease: LockLease,
        metadata: PackageCatalogMetadata | None = None,
    ) -> CatalogPackage:
        if artifact.project_uuid != lease.project_uuid:
            raise CoordinationConfigurationError(
                "The package and project lease identify different projects."
            )
        if not artifact.encryption_key_id:
            raise CoordinationConfigurationError(
                "The package does not identify its encryption key."
            )

        data = self._request_json(
            method="POST",
            path=self._package_path(artifact.project_uuid),
            payload={
                "lease_id": lease.lease_id,
                "transport_name": artifact.transport_name,
                "remote_id": artifact.remote_id,
                "project_version": artifact.project_version,
                "package_checksum": artifact.package_checksum,
                "package_size_bytes": artifact.package_size_bytes,
                "encryption_key_id": artifact.encryption_key_id,
                **(
                    {
                        "project_name": metadata.project_name,
                        "game_id": metadata.game_id,
                        "created_by": metadata.created_by,
                    }
                    if metadata is not None
                    else {}
                ),
            },
        )
        package = data.get("package")

        if not isinstance(package, dict):
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid package record."
            )

        return self._parse_catalog_package(package)

    def list_packages(self, project_uuid: str) -> list[CatalogPackage]:
        data = self._request_json(
            method="GET",
            path=self._package_path(project_uuid),
        )
        packages = data.get("packages")

        if not isinstance(packages, list):
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid package list."
            )

        parsed: list[CatalogPackage] = []

        try:
            for package in packages:
                if not isinstance(package, dict):
                    raise ValueError("Invalid package record.")
                parsed.append(CatalogPackage.from_dict(package))
        except ValueError as error:
            raise CoordinationUnavailableError(
                "The coordination provider returned invalid package data."
            ) from error

        return parsed

    def list_latest_packages(self) -> list[CatalogPackage]:
        data = self._request_json(
            method="GET",
            path=f"{self.API_PREFIX}/packages/latest",
        )
        packages = data.get("packages")

        if not isinstance(packages, list):
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid package list."
            )

        try:
            parsed: list[CatalogPackage] = []
            for package in packages:
                if not isinstance(package, dict):
                    raise ValueError("Invalid package record.")
                parsed.append(CatalogPackage.from_dict(package))
            return parsed
        except ValueError as error:
            raise CoordinationUnavailableError(
                "The coordination provider returned invalid package data."
            ) from error

    def remove_project(self, project_uuid: str) -> None:
        self._request_json(
            method="DELETE",
            path=self._package_path(project_uuid),
        )

    def get_package_encryption_key(
        self,
        key_id: str | None = None,
    ) -> PackageEncryptionKey:
        path = f"{self.API_PREFIX}/package-encryption-key"

        if key_id is not None:
            normalized_key_id = key_id.strip()

            if not normalized_key_id:
                raise CoordinationConfigurationError(
                    "Package encryption key ID is required."
                )

            path = (
                f"{self.API_PREFIX}/package-encryption-keys/"
                f"{quote(normalized_key_id, safe='')}"
            )

        data = self._request_json(
            method="GET",
            path=path,
        )
        key = data.get("key")

        if not isinstance(key, dict):
            raise CoordinationUnavailableError(
                "The coordination provider returned an invalid package key."
            )

        try:
            return PackageEncryptionKey.from_dict(key)
        except ValueError as error:
            raise CoordinationUnavailableError(
                "The coordination provider returned invalid package key data."
            ) from error

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

        if error.code == 409 and error_code == "package_version_conflict":
            raise PackageCatalogConflictError(message) from error

        if error.code == 409 and error_code == "package_key_rotated":
            raise PackageKeyRotatedError(message) from error

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
    def _package_path(project_uuid: str) -> str:
        return (
            f"{HttpCoordinationProvider.API_PREFIX}/projects/"
            f"{quote(project_uuid, safe='')}/packages"
        )

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

    @staticmethod
    def _parse_catalog_package(data: dict[str, object]) -> CatalogPackage:
        try:
            return CatalogPackage.from_dict(data)
        except ValueError as error:
            raise CoordinationUnavailableError(
                "The coordination provider returned invalid package data."
            ) from error
