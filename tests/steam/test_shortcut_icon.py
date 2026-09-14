from pathlib import Path

from app.steam.shortcut_icon import repair_steam_desktop_shortcut_icon


def test_repairs_only_save_shift_steam_shortcut(tmp_path: Path, monkeypatch) -> None:
    icon = tmp_path / "SaveShift.ico"
    icon.write_bytes(b"ico")
    shortcut = tmp_path / "Save Shift.url"
    shortcut.write_text(
        "[InternetShortcut]\n"
        "URL=steam://rungameid/5096900\n"
        "IconFile=C:\\Steam\\missing.ico\n"
        "IconIndex=0\n",
        encoding="utf-8",
    )
    other = tmp_path / "Other.url"
    other.write_text(
        "[InternetShortcut]\nURL=steam://rungameid/123\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.steam.shortcut_icon._refresh_windows_icons",
        lambda: None,
    )

    assert repair_steam_desktop_shortcut_icon(
        desktop_directory=tmp_path,
        icon_path=icon,
        force=True,
    ) == 1
    assert f"IconFile={icon.resolve()}" in shortcut.read_text(encoding="utf-8")
    assert "IconFile" not in other.read_text(encoding="utf-8")


def test_shortcut_repair_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    icon = tmp_path / "SaveShift.ico"
    icon.write_bytes(b"ico")
    shortcut = tmp_path / "Save Shift.url"
    shortcut.write_text(
        "[InternetShortcut]\n"
        "URL=steam://rungameid/5096900\n"
        f"IconFile={icon.resolve()}\n"
        "IconIndex=0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.steam.shortcut_icon._refresh_windows_icons",
        lambda: None,
    )

    assert repair_steam_desktop_shortcut_icon(
        desktop_directory=tmp_path,
        icon_path=icon,
        force=True,
    ) == 0
