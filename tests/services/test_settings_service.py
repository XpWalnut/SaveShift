from pathlib import Path

import json

from app.core.settings import (
    AppSettings,
    CoordinationGroupSettings,
    SettingsService,
)
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


def test_manual_transfer_controls_are_opt_in(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"

    assert not SettingsService.load(settings_path).manual_transfer_controls

    SettingsService.save(
        AppSettings(manual_transfer_controls=True),
        settings_path,
    )

    assert SettingsService.load(settings_path).manual_transfer_controls


def test_session_journal_prompt_preference_is_saved_and_loaded(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"

    SettingsService.save(
        AppSettings(prompt_for_session_journal=False),
        settings_path,
    )

    loaded = SettingsService.load(settings_path)

    assert not loaded.prompt_for_session_journal


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


def test_multiple_groups_and_active_group_are_protected_and_restored(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(SecretProtector, "protect", lambda value: f"safe:{value}")
    monkeypatch.setattr(
        SecretProtector,
        "unprotect",
        lambda value: value.removeprefix("safe:"),
    )
    family = CoordinationGroupSettings(
        group_id="family",
        name="Family Valheim",
        server_url="https://family.example",
        device_id="device-family",
        device_token="family-secret",
    )
    friends = CoordinationGroupSettings(
        group_id="friends",
        name="Friends V Rising",
        server_url="https://friends.example",
        device_id="device-friends",
        device_token="friends-secret",
        is_administrator=True,
    )
    settings = AppSettings(
        coordination_groups=(family, friends),
    ).with_active_group("friends")

    SettingsService.save(settings, settings_path)
    stored = settings_path.read_text(encoding="utf-8")

    assert '"device_token":' not in stored
    assert '"device_token_protected": "family-secret"' not in stored
    assert '"device_token_protected": "friends-secret"' not in stored
    assert SettingsService.load(settings_path) == settings


def test_group_can_be_renamed_without_changing_its_connection() -> None:
    group = CoordinationGroupSettings(
        group_id="family",
        name="Old name",
        server_url="https://family.example",
        device_id="device-family",
        device_token="family-secret",
    )
    settings = AppSettings(coordination_groups=(group,)).with_active_group("family")

    renamed = settings.rename_group("family", "  Family Valheim  ")

    assert renamed.active_coordination_group is not None
    assert renamed.active_coordination_group.name == "Family Valheim"
    assert renamed.coordination_server_url == "https://family.example"
    assert renamed.coordination_device_token == "family-secret"


def test_generated_cloudflare_script_name_is_not_shown_as_group_name(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "coordination_groups": [
                    {
                        "group_id": "group-1",
                        "name": "saveshift-coordination-03fcb8",
                    }
                ],
                "active_coordination_group_id": "group-1",
            }
        ),
        encoding="utf-8",
    )

    loaded = SettingsService.load(settings_path)

    assert loaded.active_coordination_group is not None
    assert loaded.active_coordination_group.name == "My Save Shift Group"


def test_legacy_single_group_is_migrated_with_stable_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(SecretProtector, "unprotect", lambda _value: "token")
    settings_path.write_text(
        json.dumps(
            {
                "coordination_enabled": True,
                "coordination_server_url": "https://original.example",
                "coordination_device_id": "device-1",
                "coordination_device_token_protected": "protected",
                "coordination_cloudflare_script_name": "Family worlds",
            }
        ),
        encoding="utf-8",
    )

    first = SettingsService.load(settings_path)
    second = SettingsService.load(settings_path)

    assert first.legacy_group_migration_pending
    assert len(first.coordination_groups) == 1
    assert first.active_coordination_group is not None
    assert first.active_coordination_group.name == "Family worlds"
    assert first.active_coordination_group.group_id == (
        second.active_coordination_group.group_id
    )
