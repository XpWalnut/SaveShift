from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Protocol


class SteamUgcVisibility(IntEnum):
    PUBLIC = 0
    FRIENDS_ONLY = 1
    PRIVATE = 2
    UNLISTED = 3


@dataclass(frozen=True)
class SteamPublishedItem:
    published_file_id: str
    user_needs_legal_agreement: bool = False


class SteamUgcClient(Protocol):
    """SDK-facing operations needed by the package blob adapter."""

    def publish_item(
        self,
        content_directory: Path,
        *,
        title: str,
        description: str,
        metadata: str,
        visibility: SteamUgcVisibility,
    ) -> SteamPublishedItem:
        ...

    def download_item(self, published_file_id: str) -> Path:
        """Download an item and return its installed content directory."""
        ...

    def delete_item(self, published_file_id: str) -> None:
        ...
