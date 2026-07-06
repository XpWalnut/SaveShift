from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import json

from app.core.logging import logger
from app.packages.checksum import calculate_checksums
from app.packages.manifest import PackageManifest


class PackageService:
    @staticmethod
    def create_package(
        game_id: str,
        project_name: str,
        root_path: Path,
        save_files: list[Path],
        output_path: Path,
        created_by: str = "Unknown",
        save_shift_version: str = "0.1.0-alpha",
        metadata: dict | None = None,
    ) -> Path:
        if not root_path.exists():
            raise FileNotFoundError(f"Root path does not exist: {root_path}")

        if not save_files:
            raise ValueError("Cannot create package without save files.")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = PackageManifest.create(
            game_id=game_id,
            project_name=project_name,
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
    def _calculate_stream_sha256(file) -> str:
        import hashlib

        sha256 = hashlib.sha256()

        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

        return sha256.hexdigest()