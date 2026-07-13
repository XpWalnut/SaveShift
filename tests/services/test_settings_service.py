from pathlib import Path

from app.core.settings import AppSettings, SettingsService


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
