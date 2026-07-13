from dataclasses import dataclass


@dataclass(frozen=True)
class UpdateRelease:
    version: str
    tag_name: str
    name: str
    notes: str
    installer_url: str
    installer_name: str
    installer_size: int
    installer_digest: str | None
    release_url: str
