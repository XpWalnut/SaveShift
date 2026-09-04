from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any


_TOKEN_PATTERN = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])')


@dataclass(frozen=True)
class SteamInstallation:
    app_id: int
    library_path: Path
    install_path: Path
    manifest_path: Path


class SteamLibraryService:
    @staticmethod
    def detect_steam_root() -> Path | None:
        configured_path = os.environ.get("SAVESHIFT_STEAM_PATH")

        if configured_path:
            configured_root = Path(configured_path).expanduser()
            return configured_root if configured_root.is_dir() else None

        for registry_path in _registry_steam_paths():
            if registry_path.is_dir():
                return registry_path

        candidates = [
            Path(program_files) / "Steam"
            for variable_name in ("ProgramFiles(x86)", "ProgramFiles")
            if (program_files := os.environ.get(variable_name))
        ]

        for candidate in candidates:
            if candidate.is_dir():
                return candidate

        return None

    @staticmethod
    def discover_library_paths(
        steam_root: Path | None = None,
    ) -> list[Path]:
        root = steam_root or SteamLibraryService.detect_steam_root()

        if root is None or not root.is_dir():
            return []

        libraries = [root]
        library_file = root / "steamapps" / "libraryfolders.vdf"
        data = _read_vdf(library_file)
        library_folders = data.get("libraryfolders", {})

        if isinstance(library_folders, dict):
            for value in library_folders.values():
                path_value = (
                    value.get("path")
                    if isinstance(value, dict)
                    else value
                )

                if isinstance(path_value, str) and path_value.strip():
                    libraries.append(Path(path_value))

        unique_libraries: list[Path] = []
        seen: set[str] = set()

        for library in libraries:
            normalized = str(library.resolve(strict=False)).casefold()

            if normalized in seen or not library.is_dir():
                continue

            seen.add(normalized)
            unique_libraries.append(library)

        return unique_libraries

    @staticmethod
    def find_installed_apps(
        steam_root: Path | None = None,
    ) -> dict[int, SteamInstallation]:
        installations: dict[int, SteamInstallation] = {}

        for library in SteamLibraryService.discover_library_paths(steam_root):
            steamapps = library / "steamapps"

            for manifest_path in steamapps.glob("appmanifest_*.acf"):
                app_state = _read_vdf(manifest_path).get("AppState", {})

                if not isinstance(app_state, dict):
                    continue

                app_id_value = app_state.get("appid")
                install_directory = app_state.get("installdir")

                try:
                    app_id = int(app_id_value)
                except (TypeError, ValueError):
                    continue

                if not isinstance(install_directory, str):
                    continue

                install_path = steamapps / "common" / install_directory

                if not install_path.is_dir():
                    continue

                installations[app_id] = SteamInstallation(
                    app_id=app_id,
                    library_path=library,
                    install_path=install_path,
                    manifest_path=manifest_path,
                )

        return installations


def _read_vdf(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}

    try:
        return _parse_vdf(text)
    except ValueError:
        return {}


def _parse_vdf(text: str) -> dict[str, Any]:
    tokens = [
        _unescape_vdf_string(match.group(1))
        if match.group(1) is not None
        else match.group(2)
        for match in _TOKEN_PATTERN.finditer(text)
    ]
    position = 0

    def parse_object(expect_closing_brace: bool) -> dict[str, Any]:
        nonlocal position
        result: dict[str, Any] = {}

        while position < len(tokens):
            token = tokens[position]

            if token == "}":
                if not expect_closing_brace:
                    raise ValueError("Unexpected closing brace in VDF data.")
                position += 1
                return result

            if token == "{":
                raise ValueError("Unexpected opening brace in VDF data.")

            key = token
            position += 1

            if position >= len(tokens):
                raise ValueError("VDF key is missing a value.")

            value = tokens[position]
            position += 1

            if value == "{":
                result[key] = parse_object(expect_closing_brace=True)
            elif value == "}":
                raise ValueError("VDF key is missing a value.")
            else:
                result[key] = value

        if expect_closing_brace:
            raise ValueError("VDF object is missing a closing brace.")

        return result

    parsed = parse_object(expect_closing_brace=False)

    if position != len(tokens):
        raise ValueError("Unexpected trailing VDF data.")

    return parsed


def _unescape_vdf_string(value: str) -> str:
    return value.replace(r'\"', '"').replace(r"\\", chr(92))


def _registry_steam_paths() -> list[Path]:
    if os.name != "nt":
        return []

    try:
        import winreg
    except ImportError:
        return []

    locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\WOW6432Node\Valve\Steam",
            "InstallPath",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"Software\Valve\Steam",
            "InstallPath",
        ),
    )
    paths: list[Path] = []

    for hive, key_path, value_name in locations:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
        except OSError:
            continue

        if isinstance(value, str) and value.strip():
            paths.append(Path(value))

    return paths
