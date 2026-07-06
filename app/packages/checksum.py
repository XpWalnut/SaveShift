from pathlib import Path
import hashlib


def calculate_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def calculate_checksums(files: list[Path], root_path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}

    for file_path in files:
        relative_path = str(file_path.relative_to(root_path)).replace("\\", "/")
        checksums[relative_path] = calculate_sha256(file_path)

    return checksums