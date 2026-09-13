import hashlib
import json
import stat
import warnings
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from app.packages import archive_policy
from app.packages.package_extractor import PackageExtractor
from app.packages.package_service import PackageService


def _manifest(files: list[str]) -> dict[str, object]:
    return {
        "package_format_version": 1,
        "project_uuid": "12345678-1234-4678-9234-567812345678",
        "project_version": 1,
        "game_id": "valheim",
        "project_name": "Mistwalkers",
        "created_at_utc": "2026-09-12T12:00:00+00:00",
        "created_by": "Jake",
        "save_shift_version": "0.1.0-alpha.4",
        "files": files,
        "metadata": {},
        "journal_entries": [],
    }


def _write_package(
    path: Path,
    files: dict[str, bytes],
    *,
    declared_files: list[str] | None = None,
) -> None:
    declared = declared_files if declared_files is not None else list(files)
    checksums = {
        name: hashlib.sha256(files[name]).hexdigest()
        for name in declared
        if name in files
    }
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as package:
        package.writestr("manifest.json", json.dumps(_manifest(declared)))
        package.writestr("checksums.json", json.dumps(checksums))
        for name, content in files.items():
            package.writestr(f"files/{name}", content)


def test_valid_package_extracts_only_declared_regular_files(tmp_path: Path) -> None:
    package_path = tmp_path / "valid.sspkg"
    _write_package(
        package_path,
        {"world.db": b"database", "nested/world.fwl": b"metadata"},
    )

    extracted = PackageExtractor.extract(package_path, tmp_path / "extracted")

    assert (extracted / "world.db").read_bytes() == b"database"
    assert (extracted / "nested" / "world.fwl").read_bytes() == b"metadata"


def test_undeclared_archive_file_is_rejected(tmp_path: Path) -> None:
    package_path = tmp_path / "undeclared.sspkg"
    _write_package(
        package_path,
        {"world.db": b"database", "payload.exe": b"not a save"},
        declared_files=["world.db"],
    )

    with pytest.raises(ValueError, match="not declared"):
        PackageService.verify_package(package_path)


def test_declared_executable_or_script_is_rejected(tmp_path: Path) -> None:
    package_path = tmp_path / "executable.sspkg"
    _write_package(package_path, {"nested/payload.exe": b"MZ"})

    with pytest.raises(ValueError, match="executable or script"):
        PackageService.verify_package(package_path)


@pytest.mark.parametrize(
    "unsafe_name",
    ["../outside.exe", "world.sav:payload.exe", "CON.txt", "nested/../world.db"],
)
def test_unsafe_save_paths_are_rejected_without_writing_outside_destination(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    package_path = tmp_path / "unsafe.sspkg"
    _write_package(package_path, {unsafe_name: b"payload"})
    destination = tmp_path / "destination"

    with pytest.raises(ValueError, match="unsafe"):
        PackageExtractor.extract(package_path, destination)

    assert not destination.exists()
    assert not (tmp_path / "outside.exe").exists()


def test_duplicate_and_case_colliding_entries_are_rejected(tmp_path: Path) -> None:
    duplicate_path = tmp_path / "duplicate.sspkg"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with ZipFile(duplicate_path, "w") as package:
            package.writestr("manifest.json", "{}")
            package.writestr("manifest.json", "{}")
            package.writestr("checksums.json", "{}")
    with pytest.raises(ValueError, match="duplicate"):
        PackageService.verify_package(duplicate_path)

    collision_path = tmp_path / "collision.sspkg"
    with ZipFile(collision_path, "w") as package:
        package.writestr("manifest.json", "{}")
        package.writestr("MANIFEST.JSON", "{}")
        package.writestr("checksums.json", "{}")
    with pytest.raises(ValueError, match="case-colliding"):
        PackageService.verify_package(collision_path)


def test_symbolic_link_entry_is_rejected(tmp_path: Path) -> None:
    package_path = tmp_path / "link.sspkg"
    content = b"outside-target"
    info = ZipInfo("files/world.db")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(package_path, "w") as package:
        package.writestr("manifest.json", json.dumps(_manifest(["world.db"])))
        package.writestr(
            "checksums.json",
            json.dumps({"world.db": hashlib.sha256(content).hexdigest()}),
        )
        package.writestr(info, content)

    with pytest.raises(ValueError, match="link or other special file"):
        PackageService.verify_package(package_path)


def test_expansion_limit_is_enforced_before_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_path = tmp_path / "oversized.sspkg"
    _write_package(package_path, {"world.db": b"123456789"})
    monkeypatch.setattr(archive_policy, "MAX_EXTRACTED_BYTES", 8)

    with pytest.raises(ValueError, match="safe extraction limit"):
        PackageExtractor.extract(package_path, tmp_path / "destination")

    assert not (tmp_path / "destination").exists()
