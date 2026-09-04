from datetime import UTC, datetime, timedelta

import pytest

from app.coordination.manager import CoordinationManager
from app.coordination.models import LockLease, PairedDevice


def _lease(project_uuid: str = "project-uuid", fencing_token: int = 1) -> LockLease:
    now = datetime.now(UTC)
    return LockLease(
        project_uuid=project_uuid,
        lease_id=f"lease-{fencing_token}",
        fencing_token=fencing_token,
        owner_device_id="device-123",
        owner_display_name="Jake",
        acquired_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )


class FakeProvider:
    def __init__(self) -> None:
        self.acquired: list[tuple[str, str]] = []
        self.renewed: list[LockLease] = []
        self.released: list[LockLease] = []
        self.renew_error: Exception | None = None

    def pair(self, pairing_code: str, device_name: str) -> PairedDevice:
        return PairedDevice("device-123", "token")

    def acquire_lock(self, project_uuid: str, owner_display_name: str) -> LockLease:
        self.acquired.append((project_uuid, owner_display_name))
        return _lease(project_uuid)

    def renew_lock(self, lease: LockLease) -> LockLease:
        self.renewed.append(lease)

        if self.renew_error:
            raise self.renew_error

        return _lease(lease.project_uuid, lease.fencing_token)

    def release_lock(self, lease: LockLease) -> None:
        self.released.append(lease)

    def get_lock(self, project_uuid: str) -> LockLease | None:
        return None


def test_hosting_lease_is_retained_and_renewed() -> None:
    provider = FakeProvider()
    manager = CoordinationManager(provider)

    acquired = manager.acquire_hosting_lease("project-uuid", "Jake")
    failures = manager.renew_active_leases()

    assert failures == []
    assert manager.active_leases["project-uuid"].lease_id == acquired.lease_id
    assert provider.acquired == [("project-uuid", "Jake")]
    assert provider.renewed == [acquired]


def test_renewal_failure_preserves_lease_for_retry() -> None:
    provider = FakeProvider()
    provider.renew_error = OSError("offline")
    manager = CoordinationManager(provider)
    lease = manager.acquire_hosting_lease("project-uuid", "Jake")

    failures = manager.renew_active_leases()

    assert failures == [(lease, provider.renew_error)]
    assert manager.active_leases["project-uuid"] == lease


def test_temporary_lease_is_released_after_success_and_failure() -> None:
    provider = FakeProvider()
    manager = CoordinationManager(provider)

    with manager.temporary_lease("first-project", "Jake"):
        assert manager.has_active_lease("first-project")

    with pytest.raises(ValueError):
        with manager.temporary_lease("second-project", "Jake"):
            raise ValueError("operation failed")

    assert not manager.active_leases
    assert [lease.project_uuid for lease in provider.released] == [
        "first-project",
        "second-project",
    ]


def test_temporary_operation_rejects_actively_hosted_project() -> None:
    manager = CoordinationManager(FakeProvider())
    manager.acquire_hosting_lease("project-uuid", "Jake")

    with pytest.raises(RuntimeError, match="Stop hosting"):
        with manager.temporary_lease("project-uuid", "Jake"):
            pass
