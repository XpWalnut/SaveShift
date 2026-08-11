from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.coordination.models import LockLease
from app.package_transport.controller import PackageHandoffController
from app.services.group_handoff_service import GroupHandoffService


def _lease() -> LockLease:
    now = datetime.now(UTC)
    return LockLease(
        project_uuid="project-123",
        lease_id="lease-1",
        fencing_token=1,
        owner_device_id="device-1",
        owner_display_name="Bob",
        acquired_at_utc=now,
        expires_at_utc=now + timedelta(minutes=15),
    )


def test_controller_publishes_away_from_caller(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    controller = PackageHandoffController()
    provider = object()
    package_path = tmp_path / "package.sspkg"
    expected = object()
    calls: list[tuple[Path, LockLease, object]] = []

    def publish(package, lease, received_provider, **_kwargs):
        calls.append((package, lease, received_provider))
        return expected

    monkeypatch.setattr(GroupHandoffService, "publish_package", publish)

    with qtbot.waitSignal(controller.publish_completed) as signal:
        assert controller.publish(package_path, _lease(), provider) is True

    assert signal.args == [expected]
    assert calls == [(package_path, _lease(), provider)]
    assert controller.running is False


def test_controller_downloads_and_reports_failure(
    qtbot,
    monkeypatch,
) -> None:
    controller = PackageHandoffController()

    def fail(*_args, **_kwargs):
        raise RuntimeError("Steam is offline")

    monkeypatch.setattr(GroupHandoffService, "download_latest", fail)

    with qtbot.waitSignal(controller.failed) as signal:
        assert controller.download_latest("project-123", object()) is True

    assert signal.args == ["Steam is offline"]
    assert controller.running is False


def test_controller_rejects_second_operation_while_running() -> None:
    controller = PackageHandoffController()
    controller._running = True

    assert controller.download_latest("project-123", object()) is False
    assert controller.publish(Path("package.sspkg"), _lease(), object()) is False
