from typing import Protocol

from app.coordination.models import (
    CoordinationDevice,
    GroupInvitation,
    GroupLeaveResult,
    LockLease,
    PairedDevice,
)


class CoordinationProvider(Protocol):
    """Provider-neutral contract consumed by Save Shift workflows."""

    def pair(self, pairing_code: str, device_name: str) -> PairedDevice:
        ...

    def acquire_lock(
        self,
        project_uuid: str,
        owner_display_name: str,
    ) -> LockLease:
        ...

    def renew_lock(self, lease: LockLease) -> LockLease:
        ...

    def release_lock(self, lease: LockLease) -> None:
        ...

    def get_lock(self, project_uuid: str) -> LockLease | None:
        ...


class GroupAdministrationProvider(Protocol):
    """Optional onboarding and administration contract for modern providers."""

    def bootstrap(self, bootstrap_token: str, device_name: str) -> PairedDevice:
        ...

    def join(self, invitation_token: str, device_name: str) -> PairedDevice:
        ...

    def create_invitation(self, expires_in_seconds: int = 86400) -> GroupInvitation:
        ...

    def list_devices(self) -> list[CoordinationDevice]:
        ...

    def revoke_device(self, device_id: str) -> None:
        ...

    def leave_group(self) -> GroupLeaveResult:
        ...
