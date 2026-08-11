from typing import Protocol

from app.coordination.models import (
    CatalogPackage,
    CoordinationDevice,
    GroupInvitation,
    GroupLeaveResult,
    LockLease,
    PackageEncryptionKey,
    PairedDevice,
)
from app.package_transport.models import PackageArtifact


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


class PackageCatalogProvider(Protocol):
    """Catalog contract kept separate from leases and package byte storage."""

    def register_package(
        self,
        artifact: PackageArtifact,
        lease: LockLease,
    ) -> CatalogPackage:
        ...

    def list_packages(self, project_uuid: str) -> list[CatalogPackage]:
        ...


class PackageKeyProvider(Protocol):
    """Authenticated access to group package encryption material."""

    def get_package_encryption_key(
        self,
        key_id: str | None = None,
    ) -> PackageEncryptionKey:
        ...
