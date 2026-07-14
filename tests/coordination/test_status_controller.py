from datetime import UTC, datetime, timedelta

from app.coordination.models import LockLease
from app.coordination.status_controller import LockStatusController


def _lease(project_uuid: str) -> LockLease:
    now = datetime.now(UTC)
    return LockLease(
        project_uuid=project_uuid,
        lease_id="lease-123",
        fencing_token=1,
        owner_device_id="device-123",
        owner_display_name="Alice",
        acquired_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )


class StatusProvider:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def get_lock(self, project_uuid: str) -> LockLease | None:
        self.requests.append(project_uuid)
        return _lease(project_uuid) if project_uuid == "locked" else None


def test_status_controller_loads_project_locks_off_the_ui_thread(qtbot) -> None:
    provider = StatusProvider()
    controller = LockStatusController()

    with qtbot.waitSignal(controller.completed, timeout=2_000) as completed:
        assert controller.refresh(provider, ["locked", "available"])

    statuses = completed.args[0]
    assert statuses["locked"].owner_display_name == "Alice"
    assert statuses["available"] is None
    assert provider.requests == ["locked", "available"]


def test_status_controller_reports_provider_failure(qtbot) -> None:
    class FailingProvider:
        def get_lock(self, _project_uuid: str) -> LockLease | None:
            raise OSError("offline")

    controller = LockStatusController()

    with qtbot.waitSignal(controller.failed, timeout=2_000) as failed:
        assert controller.refresh(FailingProvider(), ["project"])

    assert failed.args == ["offline"]
