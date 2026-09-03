from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

from app.core.settings import AppSettings, SettingsService
from app.core.distribution import DistributionChannel
from app.ui.dialogs.settings_dialog import SettingsDialog
from app.ui.main_window import MainWindow
from app.updates.controller import UpdateController
from app.updates.models import UpdateRelease
from app.updates.service import UpdateService


def _release() -> UpdateRelease:
    return UpdateRelease(
        version="0.2.0-alpha.1",
        tag_name="v0.2.0-alpha.1",
        name="Save Shift 0.2.0 alpha 1",
        notes="Updater regression release",
        installer_url=(
            "https://github.com/XpWalnut/SaveShift/releases/download/"
            "v0.2.0-alpha.1/SaveShiftSetup-0.2.0-alpha.1.exe"
        ),
        installer_name="SaveShiftSetup-0.2.0-alpha.1.exe",
        installer_size=100,
        installer_digest="sha256:" + "a" * 64,
        release_url="https://github.com/XpWalnut/SaveShift/releases/tag/v0.2.0-alpha.1",
    )


def _window(qtbot, monkeypatch: pytest.MonkeyPatch) -> MainWindow:
    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def test_settings_dialog_check_now_preserves_checkbox_and_requests_check(
    qtbot,
) -> None:
    dialog = SettingsDialog(
        settings=AppSettings(automatic_update_checks=False)
    )
    qtbot.addWidget(dialog)
    dialog.automatic_update_checkbox.setChecked(True)

    dialog.check_now_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.check_requested
    assert dialog.automatic_update_checks


def test_steam_settings_explain_that_updates_are_managed_by_steam(qtbot) -> None:
    dialog = SettingsDialog(
        settings=AppSettings(automatic_update_checks=True),
        distribution_channel=DistributionChannel.STEAM,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert not dialog.automatic_update_checkbox.isVisible()
    assert not dialog.check_now_button.isVisible()
    assert "downloaded and installed automatically by Steam" in (
        dialog.update_management_label.text()
    )


def test_settings_dialog_makes_disabled_and_unpaired_coordination_clear(
    qtbot,
) -> None:
    dialog = SettingsDialog(settings=AppSettings())
    qtbot.addWidget(dialog)

    assert "Status: Disabled" in dialog.coordination_status_label.text()
    assert not dialog.coordination_server_input.isEnabled()

    dialog.coordination_enabled_checkbox.setChecked(True)

    assert "Status: Not paired" in dialog.coordination_status_label.text()
    assert dialog.coordination_server_input.isEnabled()


def test_settings_dialog_presents_create_and_join_group_actions(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SAVESHIFT_CLOUDFLARE_OAUTH_CLIENT_ID", raising=False)
    dialog = SettingsDialog(settings=AppSettings())
    qtbot.addWidget(dialog)

    assert dialog.create_group_button.isVisible() is False
    dialog.show()
    assert dialog.create_group_button.isVisible()
    assert dialog.join_group_button.isVisible()
    assert dialog.create_group_button.isEnabled()

    dialog.create_group_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.coordination_action == "create_group"


def test_settings_dialog_shows_administrator_actions_after_pairing(qtbot) -> None:
    dialog = SettingsDialog(
        settings=AppSettings(
            coordination_enabled=True,
            coordination_device_id="device-123",
            coordination_is_administrator=True,
        )
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.create_invitation_button.isVisible()
    assert dialog.manage_devices_button.isVisible()
    assert dialog.leave_group_button.isVisible()
    assert not dialog.create_group_button.isVisible()
    assert "group administrator" in dialog.coordination_status_label.text()


def test_legacy_administrator_migration_is_kept_in_advanced_settings(qtbot) -> None:
    dialog = SettingsDialog(
        settings=AppSettings(
            coordination_enabled=True,
            coordination_device_id="legacy-device",
            coordination_is_administrator=False,
        )
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert not dialog.claim_administrator_button.isVisible()

    dialog.advanced_coordination_checkbox.setChecked(True)

    assert dialog.claim_administrator_button.isVisible()


def test_automatic_check_is_skipped_for_package_launch(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SAVESHIFT_DISABLE_UPDATE_CHECKS", raising=False)
    monkeypatch.setattr("app.ui.main_window.discover_all_projects", lambda: None)
    monkeypatch.setattr(
        "app.ui.main_window.QTimer.singleShot",
        lambda *_args: None,
    )
    window = MainWindow(startup_package_path=tmp_path / "incoming.sspkg")
    qtbot.addWidget(window)
    window.settings = AppSettings(automatic_update_checks=True)
    monkeypatch.setattr(
        window.update_controller,
        "check_for_updates",
        lambda **_kwargs: pytest.fail("update check should be skipped"),
    )

    window._start_automatic_update_check()


@pytest.mark.parametrize(
    ("automatic_update_checks", "expected_calls"),
    [(True, [False]), (False, [])],
)
def test_startup_check_respects_automatic_update_preference(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    automatic_update_checks: bool,
    expected_calls: list[bool],
) -> None:
    monkeypatch.delenv("SAVESHIFT_DISABLE_UPDATE_CHECKS", raising=False)
    monkeypatch.setattr(
        "app.ui.main_window.QTimer.singleShot",
        lambda *_args: None,
    )
    window = _window(qtbot, monkeypatch)
    window.settings = AppSettings(
        automatic_update_checks=automatic_update_checks
    )
    calls: list[bool] = []
    monkeypatch.setattr(
        window.update_controller,
        "check_for_updates",
        lambda *, manual: calls.append(manual) or True,
    )

    window._start_automatic_update_check()

    assert calls == expected_calls


def test_steam_installation_skips_github_update_checks(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.distribution_channel = DistributionChannel.STEAM
    monkeypatch.setattr(
        window.update_controller,
        "check_for_updates",
        lambda **_kwargs: pytest.fail("Steam owns this installation's updates"),
    )

    window._start_automatic_update_check()


def test_manual_check_on_steam_explains_update_ownership(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    window.distribution_channel = DistributionChannel.STEAM
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window.check_for_updates(manual=True)

    assert messages == [
        (
            "Updates Managed by Steam",
            "Steam automatically downloads and installs updates for this "
            "Save Shift installation.",
        )
    ]


def test_manual_no_update_result_reports_current_version(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.ui.main_window.QMessageBox.information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window._no_update_available(manual=True)

    assert messages == [
        (
            "No Updates Available",
            "You are using the latest available version of Save Shift.",
        )
    ]


def test_declined_update_persists_opt_out_without_downloading(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    saved_settings: list[AppSettings] = []

    class DeclinedDialog:
        automatic_update_checks = False

        def __init__(self, **_kwargs: object) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        "app.ui.main_window.UpdateAvailableDialog",
        DeclinedDialog,
    )
    monkeypatch.setattr(
        SettingsService,
        "save",
        lambda settings: saved_settings.append(settings),
    )
    monkeypatch.setattr(
        window,
        "_begin_update_download",
        lambda _release: pytest.fail("download should not begin"),
    )

    window._update_available(_release(), _manual=False)

    assert window.settings == AppSettings(automatic_update_checks=False)
    assert saved_settings == [window.settings]


def test_accepted_update_begins_installer_download(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    release = _release()
    downloads: list[UpdateRelease] = []

    class AcceptedDialog:
        automatic_update_checks = True

        def __init__(self, **_kwargs: object) -> None:
            pass

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "app.ui.main_window.UpdateAvailableDialog",
        AcceptedDialog,
    )
    monkeypatch.setattr(SettingsService, "save", lambda _settings: None)
    monkeypatch.setattr(window, "_begin_update_download", downloads.append)

    window._update_available(release, _manual=True)

    assert downloads == [release]


def test_downloaded_installer_is_launched_before_application_quits(
    qtbot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = _window(qtbot, monkeypatch)
    installer_path = tmp_path / "SaveShiftSetup-0.2.0.exe"
    installer_path.write_bytes(b"installer")
    events: list[object] = []
    monkeypatch.setattr(
        UpdateService,
        "launch_installer",
        lambda path: events.append(("launch", path)),
    )
    monkeypatch.setattr(window, "_quit_application", lambda: events.append("quit"))

    window._update_download_completed(installer_path)

    assert events == [("launch", installer_path), "quit"]


def test_update_controller_runs_check_and_emits_release(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _release()
    monkeypatch.setattr(
        UpdateService,
        "check_for_update",
        lambda: release,
    )
    controller = UpdateController()

    with qtbot.waitSignal(controller.update_available, timeout=2000) as signal:
        assert controller.check_for_updates(manual=True)

    assert signal.args == [release, True]
    qtbot.waitUntil(lambda: not controller._check_running, timeout=2000)
