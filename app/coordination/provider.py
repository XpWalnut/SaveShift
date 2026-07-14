from typing import Protocol

from app.coordination.models import LockLease, PairedDevice


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
