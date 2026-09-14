from contextlib import contextmanager
from collections.abc import Generator

from app.coordination.models import LockLease
from app.coordination.provider import CoordinationProvider


class CoordinationManager:
    """Provider-neutral lease lifecycle for desktop workflows."""

    def __init__(self, provider: CoordinationProvider) -> None:
        self.provider = provider
        self.active_leases: dict[str, LockLease] = {}

    def has_active_lease(self, project_uuid: str) -> bool:
        return project_uuid in self.active_leases

    def acquire_hosting_lease(
        self,
        project_uuid: str,
        owner_display_name: str,
    ) -> LockLease:
        acquire = getattr(self.provider, "acquire_hosting_lock", None)
        lease = (
            acquire(project_uuid, owner_display_name)
            if callable(acquire)
            else self.provider.acquire_lock(project_uuid, owner_display_name)
        )
        self.active_leases[project_uuid] = lease
        return lease

    def recover_hosting_lease(
        self,
        project_uuid: str,
        owner_display_name: str,
        parent_descriptor_hash: str,
    ) -> LockLease:
        acquire = getattr(self.provider, "acquire_recovery_lock", None)
        if not callable(acquire):
            raise RuntimeError("This coordination provider cannot recover a host session.")
        lease = acquire(
            project_uuid,
            owner_display_name,
            parent_descriptor_hash,
        )
        self.active_leases[project_uuid] = lease
        return lease

    def renew_active_leases(self) -> list[tuple[LockLease, Exception]]:
        failures: list[tuple[LockLease, Exception]] = []

        for project_uuid, lease in list(self.active_leases.items()):
            try:
                self.active_leases[project_uuid] = self.provider.renew_lock(lease)
            except Exception as error:
                failures.append((lease, error))

        return failures

    def release_lease(self, project_uuid: str) -> None:
        lease = self.active_leases.get(project_uuid)

        if lease is None:
            return

        self.provider.release_lock(lease)
        self.active_leases.pop(project_uuid, None)

    def forget_lease(self, project_uuid: str) -> None:
        self.active_leases.pop(project_uuid, None)

    def release_all(self) -> list[tuple[LockLease, Exception]]:
        failures: list[tuple[LockLease, Exception]] = []

        for project_uuid, lease in list(self.active_leases.items()):
            try:
                self.provider.release_lock(lease)
            except Exception as error:
                failures.append((lease, error))
            else:
                self.active_leases.pop(project_uuid, None)

        return failures

    def close(self) -> list[tuple[LockLease, Exception]]:
        """Release tracked leases and dispose provider-owned resources."""
        failures = self.release_all()
        close_provider = getattr(self.provider, "close", None)
        if callable(close_provider):
            close_provider()
        return failures

    @contextmanager
    def temporary_lease(
        self,
        project_uuid: str,
        owner_display_name: str,
    ) -> Generator[LockLease, None, None]:
        if self.has_active_lease(project_uuid):
            raise RuntimeError(
                "Stop hosting this project before modifying its local save."
            )

        lease = self.provider.acquire_lock(project_uuid, owner_display_name)
        self.active_leases[project_uuid] = lease

        try:
            yield lease
        finally:
            self.release_lease(project_uuid)
