from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

from app.coordination.models import CatalogPackage, LockLease
from app.coordination.provider import PackageCatalogProvider, PackageKeyProvider
from app.core.config import AppConfig
from app.core.logging import diagnostic_operation, logger
from app.package_transport.encrypted_transport import EncryptedPackageTransport
from app.package_transport.handoff_service import PackageHandoffService
from app.steam.native_ugc_client import SteamworksUgcClient
from app.steam.ugc_client import SteamUgcClient
from app.steam.ugc_transport import SteamUgcBlobTransport


class GroupHandoffService:
    """Composes the group catalog, encryption, and Steam UGC transport."""

    @staticmethod
    @diagnostic_operation("package.publish")
    def publish_package(
        package_path: Path,
        lease: LockLease,
        provider: PackageCatalogProvider | PackageKeyProvider,
        *,
        legal_agreement_handler: Callable[[str], None] | None = None,
        client_factory: Callable[[], SteamUgcClient] = SteamworksUgcClient,
    ) -> CatalogPackage:
        if not package_path.is_file():
            raise FileNotFoundError(
                f"The package to hand off does not exist: {package_path}"
            )

        client = client_factory()

        try:
            with GroupHandoffService._provider_client_scope(provider, client):
                transport = GroupHandoffService._transport(
                    client,
                    provider,
                    legal_agreement_handler,
                )
                return PackageHandoffService.publish(
                    package_path,
                    lease,
                    transport,
                    provider,
                )
        finally:
            GroupHandoffService._close_client(client)

    @staticmethod
    @diagnostic_operation("package.receive")
    def download_latest(
        project_uuid: str,
        provider: PackageCatalogProvider | PackageKeyProvider,
        *,
        client_factory: Callable[[], SteamUgcClient] = SteamworksUgcClient,
        destination_directory: Path | None = None,
    ) -> tuple[CatalogPackage, Path] | None:
        destination_root = (
            destination_directory or AppConfig.get_packages_directory()
        )
        destination_root.mkdir(parents=True, exist_ok=True)
        destination_path = (
            destination_root / f"received-{uuid4().hex}.sspkg"
        )
        client = client_factory()

        try:
            with GroupHandoffService._provider_client_scope(provider, client):
                transport = GroupHandoffService._transport(
                    client,
                    provider,
                    None,
                )
                result = PackageHandoffService.download_latest(
                    project_uuid,
                    destination_path,
                    transport,
                    provider,
                )

            if result is None:
                destination_path.unlink(missing_ok=True)

            return result
        except Exception:
            destination_path.unlink(missing_ok=True)
            raise
        finally:
            GroupHandoffService._close_client(client)

    @staticmethod
    @diagnostic_operation("catalog.list")
    def list_latest_packages(
        provider: PackageCatalogProvider,
    ) -> list[CatalogPackage]:
        packages = provider.list_latest_packages()
        logger.info("catalog.list count=%d", len(packages))
        return packages

    @staticmethod
    def _transport(
        client: SteamUgcClient,
        provider: PackageKeyProvider,
        legal_agreement_handler: Callable[[str], None] | None,
    ) -> EncryptedPackageTransport:
        blobs = SteamUgcBlobTransport(
            client,
            on_legal_agreement_required=legal_agreement_handler,
        )
        return EncryptedPackageTransport(blobs, provider)

    @staticmethod
    def _close_client(client: SteamUgcClient) -> None:
        close = getattr(client, "close", None)

        if callable(close):
            close()

    @staticmethod
    def _provider_client_scope(provider, client: SteamUgcClient):
        binder = getattr(provider, "use_ugc_client", None)
        return binder(client) if callable(binder) else nullcontext()
