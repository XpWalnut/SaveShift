from datetime import UTC, datetime

from PySide6.QtCore import Qt

from app.database.models.project import Project
from app.database.models.project_version import ProjectVersion
from app.packages.package_info import PackageInfo
from app.packages.package_metadata import PackageMetadata
from app.services.import_conflict import ImportAnalysis, ImportConflictKind
from app.ui.dialogs.import_conflict_dialog import ImportConflictDialog


def _package_info() -> PackageInfo:
    return PackageInfo(
        package_format_version=1,
        project_uuid="12345678-1234-4678-9234-567812345678",
        project_version=5,
        game_id="schedule_i",
        project_name="Metadata Empire",
        created_at_utc="2026-07-21T12:00:00+00:00",
        created_by="Alice",
        save_shift_version="0.1.0-alpha.3",
        file_count=35,
        verified=True,
        metadata=PackageMetadata(
            source_device_name="Alice's PC",
            notes="Ready for handoff",
            game_metadata={"game_version": "0.4.5f2"},
        ),
    )


def _project() -> Project:
    return Project(
        id=1,
        installed_game_id=1,
        uuid="12345678-1234-4678-9234-567812345678",
        name="Metadata Empire",
        local_path="unused-test-path",
    )


def _local_version() -> ProjectVersion:
    return ProjectVersion(
        id=1,
        project_id=1,
        version_number=4,
        created_at_utc=datetime.now(UTC).replace(tzinfo=None),
        created_by="Bob",
        source_type="HOSTED",
        package_path="unused.sspkg",
        package_checksum="a" * 64,
        parent_version_id=None,
        restored_from_version_id=None,
        lineage_name="main",
    )


def _analysis(kind: ImportConflictKind) -> ImportAnalysis:
    return ImportAnalysis(
        package_info=_package_info(),
        project=_project(),
        local_version=_local_version(),
        kind=kind,
    )


def test_fast_forward_preview_is_immediately_importable(qtbot) -> None:
    dialog = ImportConflictDialog(
        _analysis(ImportConflictKind.FAST_FORWARD)
    )
    qtbot.addWidget(dialog)

    assert dialog.status_label.text() == "Verified continuation"
    assert dialog.import_button.isEnabled()
    assert not dialog.replace_confirmation.isVisible()
    assert "Source device: Alice's PC" in dialog.details_label.text()
    assert "Game version: 0.4.5f2" in dialog.details_label.text()


def test_diverged_preview_requires_explicit_backup_acknowledgement(
    qtbot,
) -> None:
    dialog = ImportConflictDialog(_analysis(ImportConflictKind.DIVERGED))
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.status_label.text() == "History has diverged"
    assert dialog.replace_confirmation.isVisible()
    assert not dialog.import_button.isEnabled()
    assert dialog.import_button.text() == "Replace With Backup"

    qtbot.mouseClick(
        dialog.replace_confirmation,
        Qt.MouseButton.LeftButton,
    )

    assert dialog.import_button.isEnabled()


def test_group_reconciliation_is_available_with_explicit_acknowledgement(
    qtbot,
) -> None:
    dialog = ImportConflictDialog(
        _analysis(ImportConflictKind.GROUP_RECONCILIATION)
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.status_label.text() == (
        "Group handoff differs from local history"
    )
    assert dialog.replace_confirmation.isVisible()
    assert not dialog.import_button.isEnabled()
    assert dialog.import_button.text() == "Sync to Group Version"

    qtbot.mouseClick(
        dialog.replace_confirmation,
        Qt.MouseButton.LeftButton,
    )

    assert dialog.import_button.isEnabled()


def test_new_identity_with_existing_files_is_presented_as_replacement(
    qtbot,
) -> None:
    analysis = ImportAnalysis(
        package_info=_package_info(),
        project=None,
        local_version=None,
        kind=ImportConflictKind.NEW_PROJECT_REPLACE_EXISTING,
    )
    dialog = ImportConflictDialog(analysis)
    qtbot.addWidget(dialog)

    assert dialog.status_label.text() == "Existing save files found"
    assert not dialog.import_button.isEnabled()
    assert dialog.import_button.text() == "Replace With Backup"


def test_existing_unversioned_project_is_presented_for_identity_adoption(
    qtbot,
) -> None:
    analysis = ImportAnalysis(
        package_info=_package_info(),
        project=None,
        local_version=None,
        kind=ImportConflictKind.ADOPT_EXISTING_PROJECT,
        target_project=_project(),
    )
    dialog = ImportConflictDialog(analysis)
    qtbot.addWidget(dialog)

    assert dialog.status_label.text() == "Existing local project found"
    assert not dialog.import_button.isEnabled()


def test_blocked_collision_has_no_import_action(qtbot) -> None:
    dialog = ImportConflictDialog(
        _analysis(ImportConflictKind.VERSION_COLLISION)
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.status_label.text() == "Version collision blocked"
    assert not dialog.import_button.isVisible()
