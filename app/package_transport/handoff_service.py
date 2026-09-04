from pathlib import Path

from app.coordination.models import (
    CatalogPackage,
    LockLease,
    PackageCatalogMetadata,
)
from app.coordination.errors import PackageKeyRotatedError
from app.coordination.provider import PackageCatalogProvider
from app.core.logging import diagnostic_operation, logger
from app.package_transport.errors import PackageTransferIntegrityError
from app.package_transport.provider import PackageTransport
from app.package_transport.service import PackageTransferService
from app.packages.package_reader import PackageReader


class PackageHandoffService:
    """Coordinates package byte transport with the authenticated group catalog."""

    @staticmethod
    def publish(
        package_path: Path,
        lease: LockLease,
        transport: PackageTransport,
        catalog: PackageCatalogProvider,
    ) -> CatalogPackage:
        package_info = PackageReader.read(package_path)
        metadata = PackageCatalogMetadata(
            project_name=package_info.project_name,
            game_id=package_info.game_id,
            created_by=package_info.created_by,
        )

        for attempt in range(2):
            with diagnostic_operation("package.upload_and_encrypt"):
                artifact = PackageTransferService.publish(package_path, transport)

            try:
                with diagnostic_operation("catalog.register"):
                    registered = catalog.register_package(
                        artifact,
                        lease,
                        metadata,
                    )

                if registered.artifact != artifact:
                    raise PackageTransferIntegrityError(
                        "The package catalog changed the published artifact metadata."
                    )

                return registered
            except Exception as error:
                try:
                    PackageTransferService.delete(artifact, transport)
                except Exception as cleanup_error:
                    logger.warning(
                        "Could not remove orphaned package artifact %s: %s",
                        artifact.remote_id,
                        cleanup_error,
                    )

                if isinstance(error, PackageKeyRotatedError) and attempt == 0:
                    continue

                raise

        raise RuntimeError("Package publication retry did not complete.")

    @staticmethod
    def download_latest(
        project_uuid: str,
        destination_path: Path,
        transport: PackageTransport,
        catalog: PackageCatalogProvider,
    ) -> tuple[CatalogPackage, Path] | None:
        with diagnostic_operation("catalog.project_versions"):
            packages = catalog.list_packages(project_uuid)
        logger.info("catalog.project_versions count=%d", len(packages))

        if not packages:
            return None

        latest = max(
            packages,
            key=lambda package: package.artifact.project_version,
        )

        if latest.artifact.project_uuid != project_uuid:
            raise PackageTransferIntegrityError(
                "The package catalog returned an artifact for a different project."
            )

        with diagnostic_operation("package.download_decrypt_validate"):
            downloaded_path = PackageTransferService.download(
                latest.artifact,
                destination_path,
                transport,
            )
        return latest, downloaded_path
