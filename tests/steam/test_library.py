from pathlib import Path

from app.steam.library import SteamLibraryService


def _vdf_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\")


def _write_manifest(
    library: Path,
    app_id: int,
    install_directory: str,
    *,
    create_installation: bool = True,
) -> Path:
    steamapps = library / "steamapps"
    steamapps.mkdir(parents=True, exist_ok=True)
    manifest = steamapps / f"appmanifest_{app_id}.acf"
    manifest.write_text(
        (
            '"AppState"\n'
            "{\n"
            f'    "appid" "{app_id}"\n'
            f'    "installdir" "{install_directory}"\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    if create_installation:
        (steamapps / "common" / install_directory).mkdir(parents=True)

    return manifest


def test_discovers_installed_apps_across_multiple_steam_libraries(
    tmp_path: Path,
) -> None:
    steam_root = tmp_path / "Steam"
    second_library = tmp_path / "Games" / "SteamLibrary"
    (steam_root / "steamapps").mkdir(parents=True)
    second_library.mkdir(parents=True)
    (steam_root / "steamapps" / "libraryfolders.vdf").write_text(
        (
            '"libraryfolders"\n'
            "{\n"
            '    "0"\n'
            "    {\n"
            f'        "path" "{_vdf_path(steam_root)}"\n'
            "    }\n"
            '    "1"\n'
            "    {\n"
            f'        "path" "{_vdf_path(second_library)}"\n'
            "    }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    schedule_manifest = _write_manifest(
        steam_root,
        3164500,
        "Schedule I",
    )
    valheim_manifest = _write_manifest(
        second_library,
        892970,
        "Valheim",
    )

    libraries = SteamLibraryService.discover_library_paths(steam_root)
    installations = SteamLibraryService.find_installed_apps(steam_root)

    assert libraries == [steam_root, second_library]
    assert set(installations) == {3164500, 892970}
    assert installations[3164500].manifest_path == schedule_manifest
    assert installations[3164500].install_path == (
        steam_root / "steamapps" / "common" / "Schedule I"
    )
    assert installations[892970].manifest_path == valheim_manifest
    assert installations[892970].library_path == second_library


def test_ignores_stale_manifest_without_install_directory(
    tmp_path: Path,
) -> None:
    steam_root = tmp_path / "Steam"
    (steam_root / "steamapps").mkdir(parents=True)
    _write_manifest(
        steam_root,
        3164500,
        "Schedule I",
        create_installation=False,
    )

    assert SteamLibraryService.find_installed_apps(steam_root) == {}


def test_supports_legacy_libraryfolders_path_values(tmp_path: Path) -> None:
    steam_root = tmp_path / "Steam"
    second_library = tmp_path / "Legacy Steam Library"
    (steam_root / "steamapps").mkdir(parents=True)
    second_library.mkdir()
    (steam_root / "steamapps" / "libraryfolders.vdf").write_text(
        (
            '"libraryfolders"\n'
            "{\n"
            f'    "1" "{_vdf_path(second_library)}"\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    assert SteamLibraryService.discover_library_paths(steam_root) == [
        steam_root,
        second_library,
    ]


def test_configured_steam_root_environment_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    steam_root = tmp_path / "Portable Steam"
    steam_root.mkdir()
    monkeypatch.setenv("SAVESHIFT_STEAM_PATH", str(steam_root))

    assert SteamLibraryService.detect_steam_root() == steam_root
