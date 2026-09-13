from pathlib import PurePosixPath
import re
import stat
from datetime import datetime
import uuid
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo


MAX_ARCHIVE_MEMBERS = 100_002
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_EXTRACTED_BYTES = 32 * 1024 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 16 * 1024 * 1024 * 1024

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_WINDOWS_FORBIDDEN = re.compile(r'[<>:"|?*]|[\x00-\x1f]')
_EXECUTABLE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".cpl",
    ".dll",
    ".drv",
    ".exe",
    ".hta",
    ".jar",
    ".jse",
    ".lnk",
    ".msi",
    ".msp",
    ".pif",
    ".ps1",
    ".psm1",
    ".reg",
    ".scr",
    ".sys",
    ".url",
    ".vbe",
    ".vbs",
    ".wsf",
    ".wsh",
}


def validate_archive_structure(
    package: ZipFile,
) -> tuple[dict[str, object], dict[str, str], tuple[ZipInfo, ...]]:
    entries = package.infolist()
    if len(entries) > MAX_ARCHIVE_MEMBERS:
        raise ValueError("Package contains too many archive entries.")

    names = [entry.filename for entry in entries]
    if len(names) != len(set(names)):
        raise ValueError("Package contains duplicate archive entries.")
    folded_names = [name.casefold() for name in names]
    if len(folded_names) != len(set(folded_names)):
        raise ValueError("Package contains case-colliding archive entries.")

    by_name = {entry.filename: entry for entry in entries}
    required = {"manifest.json", "checksums.json"}
    missing = required - set(by_name)
    if missing:
        raise ValueError(f"Package is missing required files: {missing}")
    for name in required:
        entry = by_name[name]
        _validate_regular_entry(entry)
        if entry.file_size > MAX_METADATA_BYTES:
            raise ValueError(f"Package metadata is too large: {name}")

    manifest = _read_json_object(package, by_name["manifest.json"], "manifest")
    checksums_raw = _read_json_object(
        package,
        by_name["checksums.json"],
        "checksums",
    )
    if manifest.get("package_format_version") != 1:
        raise ValueError("Unsupported package format version.")
    _validate_manifest_fields(manifest)

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Package manifest must list at least one save file.")
    if not all(isinstance(name, str) for name in files):
        raise ValueError("Package manifest contains an invalid save-file path.")

    normalized_files = tuple(_validate_relative_path(name) for name in files)
    if len(normalized_files) != len(set(normalized_files)):
        raise ValueError("Package manifest contains duplicate save-file paths.")
    folded_files = [name.casefold() for name in normalized_files]
    if len(folded_files) != len(set(folded_files)):
        raise ValueError("Package manifest contains case-colliding save-file paths.")

    if set(checksums_raw) != set(normalized_files):
        raise ValueError("Package checksums do not exactly match its save files.")
    checksums: dict[str, str] = {}
    for name, value in checksums_raw.items():
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in value)
        ):
            raise ValueError(f"Package checksum is invalid for {name}.")
        checksums[name] = value.lower()

    expected_names = required | {f"files/{name}" for name in normalized_files}
    unexpected = set(by_name) - expected_names
    if unexpected:
        raise ValueError("Package contains files that are not declared in its manifest.")
    missing_files = expected_names - set(by_name)
    if missing_files:
        raise ValueError(f"Package is missing save file: {sorted(missing_files)[0]}")

    save_entries: list[ZipInfo] = []
    total_size = 0
    for name in normalized_files:
        entry = by_name[f"files/{name}"]
        _validate_regular_entry(entry)
        if entry.file_size > MAX_SINGLE_FILE_BYTES:
            raise ValueError(f"Package save file is too large: {name}")
        total_size += entry.file_size
        if total_size > MAX_EXTRACTED_BYTES:
            raise ValueError("Package expands beyond the safe extraction limit.")
        save_entries.append(entry)

    return manifest, checksums, tuple(save_entries)


def _read_json_object(
    package: ZipFile,
    entry: ZipInfo,
    label: str,
) -> dict[str, object]:
    import json

    try:
        value = json.loads(package.read(entry))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Package {label} is not valid JSON.") from error
    if not isinstance(value, dict):
        raise ValueError(f"Package {label} must be a JSON object.")
    return value


def _validate_relative_path(value: str) -> str:
    if not value or "\\" in value or len(value) > 4096:
        raise ValueError("Package contains an unsafe save-file path.")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix():
        raise ValueError("Package contains an unsafe save-file path.")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Package contains an unsafe save-file path.")
    for part in path.parts:
        if (
            len(part) > 255
            or part.endswith((" ", "."))
            or _WINDOWS_FORBIDDEN.search(part)
            or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
        ):
            raise ValueError("Package contains a Windows-unsafe save-file path.")
    if path.suffix.casefold() in _EXECUTABLE_SUFFIXES:
        raise ValueError("Package contains an executable or script file.")
    return path.as_posix()


def _validate_manifest_fields(manifest: dict[str, object]) -> None:
    try:
        uuid.UUID(str(manifest["project_uuid"]))
    except (KeyError, ValueError) as error:
        raise ValueError("Package manifest has an invalid project UUID.") from error
    project_version = manifest.get("project_version")
    if (
        not isinstance(project_version, int)
        or isinstance(project_version, bool)
        or project_version < 1
    ):
        raise ValueError("Package manifest has an invalid project version.")
    for field, maximum in (
        ("game_id", 100),
        ("project_name", 256),
        ("created_by", 100),
        ("save_shift_version", 100),
        ("created_at_utc", 100),
    ):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f"Package manifest has an invalid {field}.")
    try:
        created_at = datetime.fromisoformat(str(manifest["created_at_utc"]))
    except ValueError as error:
        raise ValueError("Package manifest has an invalid creation timestamp.") from error
    if created_at.tzinfo is None:
        raise ValueError("Package manifest creation timestamp needs a UTC offset.")
    if not isinstance(manifest.get("metadata", {}), dict):
        raise ValueError("Package metadata must be an object.")
    journal_entries = manifest.get("journal_entries", [])
    if not isinstance(journal_entries, list) or len(journal_entries) > 10_000:
        raise ValueError("Package contains an invalid number of journal entries.")


def _validate_regular_entry(entry: ZipInfo) -> None:
    if entry.is_dir() or entry.flag_bits & 0x1:
        raise ValueError("Package contains a directory or encrypted ZIP entry.")
    if entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
        raise ValueError("Package uses an unsupported ZIP compression method.")
    file_type = (entry.external_attr >> 16) & 0o170000
    if file_type not in {0, stat.S_IFREG}:
        raise ValueError("Package contains a link or other special file.")
