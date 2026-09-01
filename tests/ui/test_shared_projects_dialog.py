from datetime import UTC, datetime

from app.coordination.models import CatalogPackage, PackageCatalogMetadata
from app.package_transport.models import PackageArtifact
from app.ui.dialogs.shared_projects_dialog import SharedProjectsDialog


def test_shared_projects_dialog_selects_catalog_package(qtbot) -> None:
    package = CatalogPackage(
        catalog_id="catalog-1",
        artifact=PackageArtifact(
            transport_name="steam-ugc",
            remote_id="workshop-1",
            project_uuid="12345678-1234-5678-1234-567812345678",
            project_version=12,
            package_checksum="a" * 64,
            package_size_bytes=4096,
            encryption_key_id="key-1",
        ),
        published_by_device_id="device-1",
        published_at_utc=datetime.now(UTC),
        metadata=PackageCatalogMetadata(
            project_name="Weekend World",
            game_id="valheim",
            created_by="Alice",
        ),
    )
    dialog = SharedProjectsDialog([package])
    qtbot.addWidget(dialog)

    assert dialog.receive_button.isEnabled() is False
    assert "Weekend World" in dialog.project_list.item(0).text()
    assert "Version 12" in dialog.project_list.item(0).text()

    dialog.project_list.setCurrentRow(0)

    assert dialog.receive_button.isEnabled() is True
    assert dialog.selected_package is package
