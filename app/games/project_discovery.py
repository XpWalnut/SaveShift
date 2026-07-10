from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DiscoveredProject:
    name: str
    root_path: Path
    save_files: list[Path]
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ImportTarget:
    project_root: Path