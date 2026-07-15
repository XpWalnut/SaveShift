from pathlib import Path

from app.core.settings import AppSettings, SettingsService
from app.core.secrets import SecretProtector


def test_missing_settings_file_uses_automatic_update_defaults(tmp_path: Path) -> None:
    settings = SettingsService.load(tmp_path / "missing.json")

    assert settings == AppSettings(automatic_update_checks=True)


def test_settings_are_saved_and_loaded(tmp_path: Path) -> None:
    settings_path = tmp_path / "nested" / "settings.json"

    SettingsService.save(
        AppSettings(automatic_update_checks=False),
        settings_path,
    )

    assert SettingsService.load(settings_path) == AppSettings(
        automatic_update_checks=False
    )
    assert not settings_path.with_suffix(".json.tmp").exists()


def test_coordination_credential_is_protected_at_rest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(
        SecretProtector,
        "protect",
        lambda value: f"protected:{value}",
    )
    monkeypatch.setattr(
        SecretProtector,
        "unprotect",
        lambda value: value.removeprefix("protected:"),
    )
    settings = AppSettings(
        automatic_update_checks=False,
        player_display_name="Jake",
        coordination_enabled=True,
        coordination_server_url="https://locks.example.com",
        coordination_device_id="device-123",
        coordination_device_name="Gaming PC",
        coordination_device_token="plain-secret-token",
        coordination_is_administrator=True,
        coordination_provider_kind="cloudflare",
        coordination_cloudflare_account_id="account-123",
        coordination_cloudflare_script_name="saveshift-coordination-123",
    )

    SettingsService.save(settings, settings_path)

    stored = settings_path.read_text(encoding="utf-8")
    assert '"coordination_device_token_protected": "protected:plain-secret-token"' in stored
    assert '"coordination_device_token":' not in stored
    assert '"coordination_is_administrator": true' in stored
    assert SettingsService.load(settings_path) == settings


def test_invalid_settings_file_falls_back_to_defaults(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("not-json", encoding="utf-8")

    assert SettingsService.load(settings_path) == AppSettings()


def test_invalid_automatic_update_value_is_ignored(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        '{"automatic_update_checks": "no"}',
        encoding="utf-8",
    )

    assert SettingsService.load(settings_path) == AppSettings()
