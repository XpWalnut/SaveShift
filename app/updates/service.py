import hashlib
import json
from pathlib import Path
import subprocess
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from app.core.config import AppConfig
from app.updates.models import UpdateRelease
from app.version import APP_VERSION


GITHUB_RELEASES_URL = (
    "https://api.github.com/repos/XpWalnut/SaveShift/releases?per_page=20"
)
GITHUB_API_VERSION = "2026-03-10"
DEFAULT_TIMEOUT_SECONDS = 5
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


class UpdateError(RuntimeError):
    pass


class UpdateService:
    @staticmethod
    def check_for_update(
        current_version: str = APP_VERSION,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> UpdateRelease | None:
        request = Request(
            GITHUB_RELEASES_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"SaveShift/{current_version}",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
        )

        try:
            with urlopen(request, timeout=timeout) as response:
                releases = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise UpdateError(f"Could not check GitHub for updates: {error}") from error

        if not isinstance(releases, list):
            raise UpdateError("GitHub returned an unexpected releases response.")

        try:
            installed_version = Version(current_version)
        except InvalidVersion as error:
            raise UpdateError(
                f"The installed Save Shift version is invalid: {current_version}"
            ) from error

        candidates: list[tuple[Version, UpdateRelease]] = []

        for release_data in releases:
            parsed_release = UpdateService._parse_release(release_data)

            if parsed_release is None:
                continue

            try:
                release_version = Version(parsed_release.version)
            except InvalidVersion:
                continue

            if release_version > installed_version:
                candidates.append((release_version, parsed_release))

        if not candidates:
            return None

        return max(candidates, key=lambda candidate: candidate[0])[1]

    @staticmethod
    def download_installer(
        release: UpdateRelease,
        progress_callback: Callable[[int], None] | None = None,
        destination_directory: Path | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> Path:
        UpdateService._validate_installer_url(release.installer_url)
        destination_root = destination_directory or (
            AppConfig.get_temp_directory() / "updates"
        )
        destination_root.mkdir(parents=True, exist_ok=True)
        destination_path = destination_root / release.installer_name
        partial_path = destination_path.with_suffix(
            f"{destination_path.suffix}.download"
        )
        request = Request(
            release.installer_url,
            headers={"User-Agent": f"SaveShift/{APP_VERSION}"},
        )
        downloaded_size = 0
        sha256 = hashlib.sha256()

        try:
            with urlopen(request, timeout=timeout) as response, partial_path.open("wb") as output:
                while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                    output.write(chunk)
                    sha256.update(chunk)
                    downloaded_size += len(chunk)

                    if progress_callback is not None and release.installer_size > 0:
                        progress_callback(
                            min(100, int(downloaded_size * 100 / release.installer_size))
                        )
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            partial_path.unlink(missing_ok=True)
            raise UpdateError(f"Could not download the update: {error}") from error

        if release.installer_size > 0 and downloaded_size != release.installer_size:
            partial_path.unlink(missing_ok=True)
            raise UpdateError(
                "The downloaded installer size did not match the GitHub release asset."
            )

        expected_digest = UpdateService._sha256_digest(release.installer_digest)

        if expected_digest is not None and sha256.hexdigest() != expected_digest:
            partial_path.unlink(missing_ok=True)
            raise UpdateError(
                "The downloaded installer failed SHA-256 verification."
            )

        partial_path.replace(destination_path)

        if progress_callback is not None:
            progress_callback(100)

        return destination_path

    @staticmethod
    def launch_installer(installer_path: Path) -> None:
        if not installer_path.is_file():
            raise FileNotFoundError(f"Update installer does not exist: {installer_path}")

        try:
            subprocess.Popen([str(installer_path)])
        except OSError as error:
            raise UpdateError(f"Could not launch the update installer: {error}") from error

    @staticmethod
    def _parse_release(release_data: object) -> UpdateRelease | None:
        if not isinstance(release_data, dict):
            return None

        if release_data.get("draft") is True:
            return None

        tag_name = release_data.get("tag_name")

        if not isinstance(tag_name, str) or not tag_name.strip():
            return None

        version = tag_name.strip().removeprefix("v")
        expected_installer_name = f"SaveShiftSetup-{version}.exe"
        assets = release_data.get("assets")

        if not isinstance(assets, list):
            return None

        installer_asset = next(
            (
                asset
                for asset in assets
                if isinstance(asset, dict)
                and asset.get("name") == expected_installer_name
            ),
            None,
        )

        if installer_asset is None:
            return None

        installer_url = installer_asset.get("browser_download_url")
        installer_size = installer_asset.get("size", 0)

        if not isinstance(installer_url, str):
            return None

        if not isinstance(installer_size, int) or installer_size < 0:
            return None

        digest = installer_asset.get("digest")

        return UpdateRelease(
            version=version,
            tag_name=tag_name,
            name=str(release_data.get("name") or tag_name),
            notes=str(release_data.get("body") or "No release notes were provided."),
            installer_url=installer_url,
            installer_name=expected_installer_name,
            installer_size=installer_size,
            installer_digest=digest if isinstance(digest, str) else None,
            release_url=str(release_data.get("html_url") or ""),
        )

    @staticmethod
    def _validate_installer_url(installer_url: str) -> None:
        parsed_url = urlparse(installer_url)

        if parsed_url.scheme != "https" or parsed_url.hostname != "github.com":
            raise UpdateError("The release installer URL is not a trusted GitHub URL.")

    @staticmethod
    def _sha256_digest(digest: str | None) -> str | None:
        if digest is None:
            return None

        algorithm, separator, value = digest.partition(":")

        if separator != ":" or algorithm.lower() != "sha256":
            return None

        normalized_value = value.lower()

        if len(normalized_value) != 64:
            return None

        if any(character not in "0123456789abcdef" for character in normalized_value):
            return None

        return normalized_value
