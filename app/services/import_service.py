from pathlib import Path

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.database.repositories.project_repository import ProjectRepository
from app.packages.checksum import calculate_sha256
from app.packages.package_extractor import PackageExtractor
from app.packages.package_info import PackageInfo
from app.packages.package_reader import PackageReader
from app.database.repositories.installed_game_repository import InstalledGameRepository
from app.games.game_id import GameId
from app.games.registry import GameRegistry
from app.services.save_file_service import SaveFileService
from app.services.project_service import ProjectService
from app.services.project_version_service import (
    ProjectVersionService,
    ProjectVersionSource,
)
from app.coordination.local_lock import ProjectOperationLock
from app.services.session_journal_service import SessionJournalService
from app.services.import_conflict import ImportAnalysis, ImportConflictKind


class ImportService:
    @staticmethod
    def import_package(
        package_path: Path,
        imported_by: str,
        notes: str | None = None,
        allow_replace: bool = False,
        allow_group_reconciliation: bool = False,
    ):
        analysis = ImportService.analyze_import(
            package_path,
            group_authoritative=allow_group_reconciliation,
        )
        ImportService._validate_analysis(analysis, allow_replace)
        package_info = analysis.package_info
        project = analysis.project

        if project is None:
            if analysis.import_target is None:
                raise RuntimeError("The package import target was not resolved.")

            if analysis.target_project is not None:
                project = ProjectRepository.adopt_identity(
                    project_id=analysis.target_project.id,
                    project_uuid=package_info.project_uuid,
                    name=package_info.project_name,
                )
            else:
                project = ImportService._create_project_from_package(
                    package_info,
                    analysis.import_target,
                )

        with ProjectOperationLock(project.uuid, "importing into it"):
            if analysis.project is not None:
                analysis = ImportService.analyze_import(
                    package_path,
                    group_authoritative=allow_group_reconciliation,
                )
                ImportService._validate_analysis(analysis, allow_replace)
                package_info = analysis.package_info
                project = analysis.project

                if project is None:
                    raise RuntimeError(
                        "The project changed while the import was being prepared."
                    )

            return ImportService._synchronize_package(
                package_path=package_path,
                package_info=package_info,
                project=project,
                imported_by=imported_by,
                notes=notes,
            )

    @staticmethod
    def _synchronize_package(
        package_path: Path,
        package_info: PackageInfo,
        project: Project,
        imported_by: str,
        notes: str | None,
    ):
        extracted_path = PackageExtractor.extract(package_path)

        project_root = Path(project.local_path)

        backup_path = None

        if project_root.exists():
            backup_path = SaveFileService.backup_project(
                project=project,
                game_id=package_info.game_id,
            )

        SaveFileService.synchronize_project(
            project=project,
            source_directory=extracted_path,
            game_id=package_info.game_id,
        )

        package_checksum = calculate_sha256(package_path)
        parent_version = ProjectVersionService.get_latest_version(project.id)
        parent_matches = ImportService._matches_package_parent(
            package_info,
            parent_version,
        )

        version = ProjectVersionService.create_version(
            project_id=project.id,
            created_by=imported_by,
            source_type=ProjectVersionSource.IMPORTED,
            version_number=package_info.project_version,
            package_path=str(package_path),
            backup_path=str(backup_path) if backup_path is not None else None,
            package_checksum=package_checksum,
            parent_version_id=(
                parent_version.id
                if parent_matches and parent_version is not None
                else None
            ),
            lineage_name=package_info.metadata.lineage_name,
            notes=(
                notes
                if notes is not None
                else package_info.metadata.notes
            ),
        )

        SessionJournalService.import_entries(
            project.id,
            package_info.journal_entries,
        )

        return version

    @staticmethod
    def _matches_package_parent(
        package_info: PackageInfo,
        local_version: ProjectVersion | None,
    ) -> bool:
        if local_version is None:
            return False

        metadata = package_info.metadata

        if metadata.parent_project_version != local_version.version_number:
            return False

        if metadata.parent_package_checksum is None:
            return True

        return (
            local_version.package_checksum
            == metadata.parent_package_checksum
        )

    @staticmethod
    def validate_import_package(package_path: Path) -> PackageInfo:
        analysis = ImportService.analyze_import(package_path)
        ImportService._raise_blocked_analysis(analysis)
        return analysis.package_info

    @staticmethod
    def analyze_import(
        package_path: Path,
        *,
        group_authoritative: bool = False,
    ) -> ImportAnalysis:
        package_info = PackageReader.read(package_path)
        project = ProjectRepository.get_by_uuid(package_info.project_uuid)

        if project is None:
            import_target = ImportService._resolve_import_target(package_info)
            target_project = ImportService._find_target_project(
                package_info,
                import_target,
            )

            if target_project is not None:
                target_version = ProjectVersionService.get_latest_version(
                    target_project.id
                )
                return ImportAnalysis(
                    package_info=package_info,
                    project=None,
                    local_version=target_version,
                    kind=(
                        ImportConflictKind.IDENTITY_COLLISION
                        if target_version is not None
                        else ImportConflictKind.ADOPT_EXISTING_PROJECT
                    ),
                    import_target=import_target,
                    target_project=target_project,
                )

            target_contains_files = ImportService._target_contains_save_files(
                package_info,
                import_target,
            )
            return ImportAnalysis(
                package_info=package_info,
                project=None,
                local_version=None,
                kind=(
                    ImportConflictKind.NEW_PROJECT_REPLACE_EXISTING
                    if target_contains_files
                    else ImportConflictKind.NEW_PROJECT
                ),
                import_target=import_target,
            )

        latest_version = ProjectVersionService.get_latest_version(project.id)

        if latest_version is None:
            return ImportAnalysis(
                package_info=package_info,
                project=project,
                local_version=None,
                kind=ImportConflictKind.REPLACE_UNVERSIONED,
            )

        local_version_number = latest_version.version_number
        incoming_version_number = package_info.project_version

        if incoming_version_number < local_version_number:
            kind = (
                ImportConflictKind.GROUP_RECONCILIATION
                if group_authoritative
                else ImportConflictKind.OLDER
            )
        elif incoming_version_number == local_version_number:
            incoming_checksum = calculate_sha256(package_path)
            kind = (
                ImportConflictKind.DUPLICATE
                if latest_version.package_checksum == incoming_checksum
                else (
                    ImportConflictKind.GROUP_RECONCILIATION
                    if group_authoritative
                    else ImportConflictKind.VERSION_COLLISION
                )
            )
        elif ImportService._matches_package_parent(
            package_info,
            latest_version,
        ):
            kind = ImportConflictKind.FAST_FORWARD
        elif (
            package_info.metadata.parent_project_version is None
            or package_info.metadata.parent_project_version
            > local_version_number
        ):
            kind = ImportConflictKind.UNVERIFIED_NEWER
        else:
            kind = ImportConflictKind.DIVERGED

        return ImportAnalysis(
            package_info=package_info,
            project=project,
            local_version=latest_version,
            kind=kind,
        )

    @staticmethod
    def _validate_analysis(
        analysis: ImportAnalysis,
        allow_replace: bool,
    ) -> None:
        ImportService._raise_blocked_analysis(analysis)

        if analysis.requires_replace_confirmation and not allow_replace:
            raise ValueError(
                "This import requires explicit confirmation to replace the "
                "current save after creating a backup."
            )

    @staticmethod
    def _raise_blocked_analysis(analysis: ImportAnalysis) -> None:
        package_version = analysis.package_info.project_version
        local_version = analysis.local_version
        current_version = (
            local_version.version_number
            if local_version is not None
            else None
        )

        if analysis.kind == ImportConflictKind.OLDER:
            raise ValueError(
                "The package is older than your current project.\n\n"
                f"Current version: {current_version}\n"
                f"Package version: {package_version}\n\n"
                "Use version history to restore an older version without "
                "corrupting the project timeline."
            )

        if analysis.kind == ImportConflictKind.DUPLICATE:
            raise ValueError(
                "This package version has already been imported.\n\n"
                f"Current version: {current_version}\n"
                f"Package version: {package_version}"
            )

        if analysis.kind == ImportConflictKind.VERSION_COLLISION:
            raise ValueError(
                "This package uses the current version number but contains "
                "different data.\n\n"
                f"Current version: {current_version}\n"
                f"Package version: {package_version}\n\n"
                "Save Shift cannot safely place both states at the same "
                "point in history."
            )

        if analysis.kind == ImportConflictKind.IDENTITY_COLLISION:
            raise ValueError(
                "A differently identified project already tracks this save "
                "folder and has its own version history. Save Shift cannot "
                "safely combine the two timelines automatically."
            )

    @staticmethod
    def _create_project_from_package(
        package_info: PackageInfo,
        import_target: Path,
    ) -> Project:
        installed_game = InstalledGameRepository.get_by_game_id(
            package_info.game_id
        )

        if installed_game is None:
            raise ValueError(
                f"This package is for {package_info.game_id}, but that "
                "game is not configured on this computer."
            )

        return ProjectService.create_project(
            installed_game_id=installed_game.id,
            project_uuid=package_info.project_uuid,
            name=package_info.project_name,
            local_path=import_target,
        )

    @staticmethod
    def _resolve_import_target(package_info: PackageInfo) -> Path:
        installed_game = InstalledGameRepository.get_by_game_id(package_info.game_id)

        if installed_game is None:
            raise ValueError(
                f"This package is for {package_info.game_id}, but that game is not configured on this computer."
            )

        supported_game = GameRegistry.get_by_game_id(package_info.game_id)

        if supported_game is None:
            raise ValueError(f"Unsupported game ID: {package_info.game_id}")


        import_target = supported_game.discovery().get_import_target(
            save_path=Path(installed_game.save_path),
            project_name=package_info.project_name,
            game_metadata=package_info.metadata.game_metadata,
        )

        return import_target.project_root

    @staticmethod
    def _find_target_project(
        package_info: PackageInfo,
        import_target: Path,
    ) -> Project | None:
        installed_game = InstalledGameRepository.get_by_game_id(
            package_info.game_id
        )

        if installed_game is None:
            return None

        expected_path = str(import_target.resolve(strict=False)).casefold()
        candidates = [
            project
            for project in ProjectRepository.get_for_installed_game(
                installed_game.id
            )
            if str(
                Path(project.local_path).resolve(strict=False)
            ).casefold() == expected_path
        ]

        for candidate in candidates:
            if candidate.name.casefold() == package_info.project_name.casefold():
                return candidate

        if ImportService._is_flat_valheim_package(package_info):
            # Legacy Valheim worlds intentionally share `worlds_local`.
            # A different project at the same path is not an identity collision.
            return None

        return candidates[0] if candidates else None

    @staticmethod
    def _target_contains_save_files(
        package_info: PackageInfo,
        import_target: Path,
    ) -> bool:
        if not import_target.is_dir():
            return False

        if ImportService._is_flat_valheim_package(package_info):
            return any(
                (import_target / f"{package_info.project_name}{suffix}").is_file()
                for suffix in (".db", ".fwl")
            )

        return any(path.is_file() for path in import_target.rglob("*"))

    @staticmethod
    def _is_flat_valheim_package(package_info: PackageInfo) -> bool:
        return (
            package_info.game_id == GameId.VALHEIM.value
            and package_info.metadata.game_metadata.get("storage_layout")
            != "chunked_directory"
        )
