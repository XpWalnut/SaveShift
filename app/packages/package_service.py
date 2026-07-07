from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import json
import hashlib
from typing import BinaryIO
from datetime import UTC, datetime
import re

from app.core.config import AppConfig
from app.core.logging import logger
from app.database.models.project import Project
from app.packages.checksum import calculate_checksums
from app.packages.package_manifest import PackageManifest


class PackageService:
    @staticmethod
    def create_package(
        game_id: str,
        project: Project,
        root_path: Path,
        save_files: list[Path],
        output_path: Path,
        created_by: str = "Unknown",
        save_shift_version: str = "0.1.0-alpha",
        metadata: dict | None = None,
    ) -> Path:
        PackageService._validate_package_inputs(
            root_path=root_path,
            save_files=save_files,
            output_path=output_path,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = PackageManifest.create(
            game_id=game_id,
            project=project,
            created_by=created_by,
            save_shift_version=save_shift_version,
            files=save_files,
            root_path=root_path,
            metadata=metadata,
        )

        checksums = calculate_checksums(save_files, root_path)

        logger.info("Creating Save Shift package: %s", output_path)

        with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as package:
            package.writestr("manifest.json", json.dumps(manifest.to_dict(), indent=2))
            package.writestr("checksums.json", json.dumps(checksums, indent=2))

            for save_file in save_files:
                relative_path = save_file.relative_to(root_path)
                archive_path = Path("files") / relative_path
                package.write(save_file, archive_path.as_posix())

        PackageService.verify_package(output_path)

        logger.info("Package created and verified: %s", output_path)

        return output_path

    @staticmethod
    def create_project_package(
            game_id: str,
            project_name: str,
            project_uuid: str,
            root_path: Path,
            save_files: list[Path],
            created_by: str,
            save_shift_version: str = "0.1.0-alpha",
            metadata: dict | None = None,
    ) -> Path:
        safe_game_id = PackageService._sanitize_path_component(game_id)
        safe_project_name = PackageService._sanitize_path_component(project_name)

        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")

        output_directory = (
                AppConfig.get_packages_directory()
                / safe_game_id
                / safe_project_name
        )

        output_path = output_directory / f"{timestamp}.sspkg"

        return PackageService.create_package(
            game_id=game_id,
            project_name=project_name,
            project_uuid=project_uuid,
            root_path=root_path,
            save_files=save_files,
            output_path=output_path,
            created_by=created_by,
            save_shift_version=save_shift_version,
            metadata=metadata,
        )

    @staticmethod
    def verify_package(package_path: Path) -> bool:
        if not package_path.exists():
            raise FileNotFoundError(f"Package does not exist: {package_path}")

        with ZipFile(package_path, "r") as package:
            required_files = {"manifest.json", "checksums.json"}
            package_names = set(package.namelist())

            missing = required_files - package_names
            if missing:
                raise ValueError(f"Package is missing required files: {missing}")

            manifest = json.loads(package.read("manifest.json"))
            checksums = json.loads(package.read("checksums.json"))

            for relative_file in manifest["files"]:
                archived_path = f"files/{relative_file}"

                if archived_path not in package_names:
                    raise ValueError(f"Package is missing save file: {archived_path}")

                with package.open(archived_path) as file:
                    actual_checksum = PackageService._calculate_stream_sha256(file)

                expected_checksum = checksums.get(relative_file)

                if expected_checksum != actual_checksum:
                    raise ValueError(f"Checksum mismatch for {relative_file}")

        return True

    @staticmethod
    def _sanitize_path_component(value: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_")

        if not sanitized:
            return "unknown"

        return sanitized

    @staticmethod
    def _validate_package_inputs(
        root_path: Path,
        save_files: list[Path],
        output_path: Path,
    ) -> None:
        if not root_path.exists():
            raise FileNotFoundError(f"Root path does not exist: {root_path}")

        if not root_path.is_dir():
            raise NotADirectoryError(f"Root path is not a directory: {root_path}")

        if not save_files:
            raise ValueError("Cannot create package without save files.")

        resolved_root = root_path.resolve()

        for save_file in save_files:
            if not save_file.exists():
                raise FileNotFoundError(f"Save file does not exist: {save_file}")

            if not save_file.is_file():
                raise ValueError(f"Save path is not a file: {save_file}")

            resolved_file = save_file.resolve()

            if not resolved_file.is_relative_to(resolved_root):
                raise ValueError(
                    f"Save file is outside the project root: {save_file}"
                )

        if output_path.exists() and output_path.is_dir():
            raise IsADirectoryError(f"Output path is a directory: {output_path}")

    @staticmethod
    def _calculate_stream_sha256(file: BinaryIO) -> str:
        sha256 = hashlib.sha256()

        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

        return sha256.hexdigest()