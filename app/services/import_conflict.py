from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.packages.package_info import PackageInfo


class ImportConflictKind(str, Enum):
    NEW_PROJECT = "new_project"
    NEW_PROJECT_REPLACE_EXISTING = "new_project_replace_existing"
    ADOPT_EXISTING_PROJECT = "adopt_existing_project"
    IDENTITY_COLLISION = "identity_collision"
    FAST_FORWARD = "fast_forward"
    REPLACE_UNVERSIONED = "replace_unversioned"
    UNVERIFIED_NEWER = "unverified_newer"
    DIVERGED = "diverged"
    GROUP_RECONCILIATION = "group_reconciliation"
    OLDER = "older"
    DUPLICATE = "duplicate"
    VERSION_COLLISION = "version_collision"


@dataclass(frozen=True)
class ImportAnalysis:
    package_info: PackageInfo
    project: Project | None
    local_version: ProjectVersion | None
    kind: ImportConflictKind
    import_target: Path | None = None
    target_project: Project | None = None

    @property
    def is_blocked(self) -> bool:
        return self.kind in {
            ImportConflictKind.OLDER,
            ImportConflictKind.DUPLICATE,
            ImportConflictKind.VERSION_COLLISION,
            ImportConflictKind.IDENTITY_COLLISION,
        }

    @property
    def requires_replace_confirmation(self) -> bool:
        return self.kind in {
            ImportConflictKind.REPLACE_UNVERSIONED,
            ImportConflictKind.NEW_PROJECT_REPLACE_EXISTING,
            ImportConflictKind.ADOPT_EXISTING_PROJECT,
            ImportConflictKind.UNVERIFIED_NEWER,
            ImportConflictKind.DIVERGED,
            ImportConflictKind.GROUP_RECONCILIATION,
        }
