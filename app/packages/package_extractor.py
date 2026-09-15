from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile
import re
import secrets
import shutil

from app.core.config import AppConfig
from app.core.logging import logger
from app.packages.package_reader import PackageReader
from app.packages.archive_policy import validate_archive_structure


class PackageExtractor:
    @staticmethod
    def extract(package_path: Path, destination: Path | None = None) -> Path:
        package_info = PackageReader.read(package_path)

        extraction_root = destination or PackageExtractor._create_temp_import_directory(
            project_name=package_info.project_name
        )

        if extraction_root.exists():
            shutil.rmtree(extraction_root)

        extraction_root.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Extracting package %s to %s",
            package_path,
            extraction_root,
        )

        try:
            resolved_root = extraction_root.resolve()
            with ZipFile(package_path, "r") as package:
                _manifest, _checksums, save_entries = validate_archive_structure(
                    package
                )
                for entry in save_entries:
                    relative_name = entry.filename.removeprefix("files/")
                    target_path = extraction_root / Path(relative_name)
                    if not target_path.resolve().is_relative_to(resolved_root):
                        raise ValueError("Package extraction path escaped its boundary.")
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    with package.open(entry) as source, target_path.open("xb") as target:
                        shutil.copyfileobj(source, target, length=1024 * 1024)
        except Exception:
            shutil.rmtree(extraction_root, ignore_errors=True)
            raise

        logger.info("Package extracted successfully to %s", extraction_root)

        return extraction_root

    @staticmethod
    def _create_temp_import_directory(project_name: str) -> Path:
        safe_project_name = PackageExtractor._sanitize_directory_name(project_name)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        suffix = secrets.token_hex(3)

        return (
            AppConfig.get_temp_directory()
            / "imports"
            / f"{safe_project_name}_{timestamp}_{suffix}"
        )

    @staticmethod
    def _sanitize_directory_name(name: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_")

        if not sanitized:
            return "package"

        return sanitized
