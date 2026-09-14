from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import threading
from typing import NoReturn
import uuid

from app.coordination.errors import (
    CoordinationConfigurationError,
    CoordinationUnavailableError,
    LockConflictError,
    LockOwnershipError,
    PackageCatalogConflictError,
    PackageKeyRotatedError,
)
from app.coordination.models import (
    CatalogPackage,
    LockLease,
    PackageCatalogMetadata,
    PackageEncryptionKey,
)
from app.core.logging import logger
from app.package_transport.models import PackageArtifact
from app.steam.device_identity import SteamDeviceIdentity, SteamDeviceIdentityStore
from app.steam.group_manifest import SteamGroupManifest
from app.steam.group_manifest_transport import SteamGroupManifestTransport
from app.steam.hosting_presence import (
    SteamHostPresence,
    SteamHostingPresenceService,
)
from app.steam.host_session_store import SteamHostSessionCheckpoint
from app.steam.manifest_cache import SteamGroupManifestCache
from app.steam.native_ugc_client import SteamworksUgcClient
from app.steam.package_descriptor import SteamPackageDescriptor
from app.steam.package_descriptor_transport import SteamPackageDescriptorTransport
from app.steam.package_discovery import (
    RejectedSteamPackage,
    SteamGroupPackageDiscovery,
)
from app.steam.package_index_transport import SteamMemberPackageIndexTransport
from app.steam.package_lineage import SteamPackageForkError
from app.steam.ugc_client import SteamUgcClient


_KEY_PREFIX = "steam-group"


@dataclass(frozen=True)
class _LeaseState:
    lease: LockLease
    parent_descriptor_hash: str
    presence: SteamHostPresence | None = None
    client: SteamUgcClient | None = None


class SteamNativeCoordinationProvider:
    """Steam-backed package catalog with online ancestry-guarded leases."""

    def __init__(
        self,
        *,
        group_id: str,
        manifest_item_id: str,
        package_index_item_id: str,
        device_id: str,
        client_factory: Callable[[], SteamUgcClient] = SteamworksUgcClient,
        identity_store: SteamDeviceIdentityStore | None = None,
        lease_seconds: int = 900,
        manifest_cache: SteamGroupManifestCache | None = None,
    ) -> None:
        self.group_id = str(uuid.UUID(group_id))
        self.manifest_item_id = self._item_id(manifest_item_id, "manifest")
        self.package_index_item_id = self._item_id(
            package_index_item_id,
            "package index",
        )
        self.device_id = str(uuid.UUID(device_id))
        self.client_factory = client_factory
        self.identity_store = identity_store or SteamDeviceIdentityStore()
        self.lease_seconds = max(60, int(lease_seconds))
        self.manifest_cache = manifest_cache or SteamGroupManifestCache()
        self._leases: dict[str, _LeaseState] = {}
        self._lease_guard = threading.RLock()
        self._publication_guard = threading.RLock()
        self._bound = threading.local()

    @contextmanager
    def use_ugc_client(self, client: SteamUgcClient) -> Generator[None, None, None]:
        if getattr(self._bound, "client", None) is not None:
            raise RuntimeError("A Steam UGC operation is already active.")
        self._bound.client = client
        try:
            yield
        finally:
            self._bound.client = None

    def pair(self, pairing_code: str, device_name: str) -> NoReturn:
        raise CoordinationConfigurationError(
            "Steam-native groups use Steam friend invitations instead of pairing codes."
        )

    def acquire_lock(
        self,
        project_uuid: str,
        owner_display_name: str,
    ) -> LockLease:
        project_id = str(uuid.UUID(project_uuid))
        owner = owner_display_name.strip()
        if not owner:
            raise CoordinationConfigurationError("A host display name is required.")
        with self._client() as client:
            manifest, identity = self._context(client)
            parent_hash = self._single_head_hash(client, manifest, project_id)
        now = datetime.now(UTC)
        lease = LockLease(
            project_uuid=project_id,
            lease_id=str(uuid.uuid4()),
            fencing_token=int(now.timestamp() * 1_000_000),
            owner_device_id=identity.device_id,
            owner_display_name=owner,
            acquired_at_utc=now,
            expires_at_utc=now + timedelta(seconds=self.lease_seconds),
        )
        with self._lease_guard:
            existing = self._leases.get(project_id)
            if existing is not None and not existing.lease.expired:
                raise LockOwnershipError("This computer is already hosting the world.")
            self._leases[project_id] = _LeaseState(lease, parent_hash)
        return lease

    def acquire_hosting_lock(
        self,
        project_uuid: str,
        owner_display_name: str,
    ) -> LockLease:
        """Acquire an ancestry guard plus an advisory searchable Steam lobby."""
        return self._acquire_hosting_lock(
            project_uuid,
            owner_display_name,
            expected_parent_hash=None,
        )

    def acquire_recovery_lock(
        self,
        project_uuid: str,
        owner_display_name: str,
        parent_descriptor_hash: str,
    ) -> LockLease:
        """Reacquire presence without rebasing interrupted local work."""
        return self._acquire_hosting_lock(
            project_uuid,
            owner_display_name,
            expected_parent_hash=parent_descriptor_hash.strip().lower(),
        )

    def _acquire_hosting_lock(
        self,
        project_uuid: str,
        owner_display_name: str,
        *,
        expected_parent_hash: str | None,
    ) -> LockLease:
        project_id = str(uuid.UUID(project_uuid))
        owner = owner_display_name.strip()
        if not owner:
            raise CoordinationConfigurationError("A host display name is required.")
        with self._lease_guard:
            existing_local = self._leases.get(project_id)
            if existing_local is not None and not existing_local.lease.expired:
                raise LockOwnershipError("This computer is already hosting the world.")

        client = self.client_factory()
        try:
            manifest, identity = self._context(client)
            service = SteamHostingPresenceService(client)
            existing = service.find(manifest, project_uuids=[project_id]).get(
                project_id
            )
            if existing is not None:
                raise LockConflictError(
                    f"{existing.host_display_name} is already hosting this world.",
                    existing.to_lease(),
                )
            parent_hash = self._single_head_hash(client, manifest, project_id)
            if (
                expected_parent_hash is not None
                and parent_hash != expected_parent_hash
            ):
                raise PackageCatalogConflictError(
                    "The group save advanced while this computer's hosted "
                    "session was interrupted. The local save was kept as a "
                    "fork and was not uploaded."
                )
            _lobby, presence = service.create(
                manifest=manifest,
                identity=identity,
                project_uuid=project_id,
                host_display_name=owner,
            )

            # This reduces the ordinary simultaneous-click race. Steam lobbies
            # remain advisory; the package ancestry check is the final guard.
            visible = service.find(manifest, project_uuids=[project_id]).get(
                project_id
            )
            if visible is not None and visible.lease_id != presence.lease_id:
                service.release(presence)
                raise LockConflictError(
                    f"{visible.host_display_name} acquired the Steam hosting "
                    "presence first.",
                    visible.to_lease(),
                )

            lease = presence.to_lease(visible_seconds=self.lease_seconds)
            with self._lease_guard:
                self._leases[project_id] = _LeaseState(
                    lease,
                    parent_hash,
                    presence,
                    client,
                )
            return lease
        except (
            LockConflictError,
            LockOwnershipError,
            PackageCatalogConflictError,
        ):
            self._close_client(client)
            raise
        except Exception as error:
            self._close_client(client)
            raise CoordinationUnavailableError(
                f"Steam could not establish the hosting presence: {error}"
            ) from error

    def host_session_checkpoint(
        self,
        lease: LockLease,
    ) -> SteamHostSessionCheckpoint:
        with self._lease_guard:
            state = self._owned_state(lease)
        if state.presence is None:
            raise LockOwnershipError("This lease is not a Steam hosting session.")
        return SteamHostSessionCheckpoint.create(
            group_id=self.group_id,
            project_uuid=lease.project_uuid,
            parent_descriptor_hash=state.parent_descriptor_hash,
            host_display_name=lease.owner_display_name,
        )

    def renew_lock(self, lease: LockLease) -> LockLease:
        with self._lease_guard:
            state = self._owned_state(lease)
            if state.presence is not None and state.client is not None:
                try:
                    poll = getattr(state.client, "poll_social_events", None)
                    if callable(poll):
                        poll()
                    SteamHostingPresenceService(state.client).verify_owned(
                        state.presence
                    )
                except ValueError as error:
                    self._leases.pop(lease.project_uuid, None)
                    self._close_client(state.client)
                    raise LockOwnershipError(str(error)) from error
                except Exception as error:
                    raise CoordinationUnavailableError(
                        f"Steam could not refresh the hosting presence: {error}"
                    ) from error
            renewed = LockLease(
                project_uuid=lease.project_uuid,
                lease_id=lease.lease_id,
                fencing_token=lease.fencing_token,
                owner_device_id=lease.owner_device_id,
                owner_display_name=lease.owner_display_name,
                acquired_at_utc=lease.acquired_at_utc,
                expires_at_utc=datetime.now(UTC)
                + timedelta(seconds=self.lease_seconds),
            )
            self._leases[lease.project_uuid] = _LeaseState(
                renewed,
                state.parent_descriptor_hash,
                state.presence,
                state.client,
            )
            return renewed

    def release_lock(self, lease: LockLease) -> None:
        with self._lease_guard:
            state = self._owned_state(lease)
            self._leases.pop(lease.project_uuid, None)
        if state.presence is not None and state.client is not None:
            try:
                SteamHostingPresenceService(state.client).release(state.presence)
            except Exception as error:
                logger.warning(
                    "Could not explicitly leave Steam hosting lobby %s: %s",
                    state.presence.lobby_id,
                    error,
                )
            finally:
                self._close_client(state.client)

    def get_lock(self, project_uuid: str) -> LockLease | None:
        project_id = str(uuid.UUID(project_uuid))
        return self.get_locks([project_id])[project_id]

    def get_locks(
        self,
        project_uuids: Iterable[str],
    ) -> dict[str, LockLease | None]:
        project_ids = [str(uuid.UUID(item)) for item in project_uuids]
        statuses: dict[str, LockLease | None] = {}
        expired_states: list[_LeaseState] = []
        with self._lease_guard:
            for project_id in project_ids:
                state = self._leases.get(project_id)
                if state is not None and not state.lease.expired:
                    statuses[project_id] = state.lease
                else:
                    if state is not None:
                        self._leases.pop(project_id, None)
                        expired_states.append(state)
                    statuses[project_id] = None
        for state in expired_states:
            self._dispose_state(state)
        missing = [item for item, value in statuses.items() if value is None]
        if not missing:
            return statuses
        try:
            with self._client() as client:
                manifest, _identity = self._context(client)
                found = SteamHostingPresenceService(client).find(
                    manifest,
                    project_uuids=missing,
                )
        except Exception as error:
            raise CoordinationUnavailableError(
                f"Steam could not check current hosting status: {error}"
            ) from error
        for project_id, presence in found.items():
            statuses[project_id] = presence.to_lease()
        return statuses

    def close(self) -> None:
        """Best-effort cleanup for all provider-owned Steam lobby clients."""
        with self._lease_guard:
            states = list(self._leases.values())
            self._leases.clear()
        for state in states:
            self._dispose_state(state)

    @contextmanager
    def ugc_client_scope(self) -> Generator[SteamUgcClient, None, None]:
        with self._client() as client:
            yield client

    def get_package_encryption_key(
        self,
        key_id: str | None = None,
    ) -> PackageEncryptionKey:
        with self._client() as client:
            manifest, identity = self._context(client)
            epoch = manifest.key_epoch if key_id is None else self._key_epoch(key_id)
            return PackageEncryptionKey(
                key_id=self._key_id(epoch),
                algorithm="AES-256-GCM",
                key_material=manifest.group_key_for(identity, epoch),
            )

    def register_package(
        self,
        artifact: PackageArtifact,
        lease: LockLease,
        metadata: PackageCatalogMetadata | None = None,
    ) -> CatalogPackage:
        if artifact.project_uuid != lease.project_uuid:
            raise CoordinationConfigurationError(
                "The package and Steam lease identify different worlds."
            )
        if metadata is None:
            raise CoordinationConfigurationError(
                "Steam package publication requires project display metadata."
            )
        with self._lease_guard:
            state = self._owned_state(lease)
        with self._publication_guard:
            with self._client() as client:
                manifest, identity = self._context(client)
                if artifact.encryption_key_id != self._key_id(manifest.key_epoch):
                    raise PackageKeyRotatedError(
                        "The Steam group key changed while the package was uploading."
                    )
                current_parent = self._single_head_hash(
                    client,
                    manifest,
                    artifact.project_uuid,
                )
                if current_parent != state.parent_descriptor_hash:
                    raise PackageCatalogConflictError(
                        "Another group member published from the starting version. "
                        "Your local save was retained as a fork and was not handed off."
                    )
                descriptor = SteamPackageDescriptorTransport(client).attach(
                    artifact,
                    manifest=manifest,
                    publisher=identity,
                    parent_descriptor_hash=state.parent_descriptor_hash or None,
                    project_name=metadata.project_name,
                    game_id=metadata.game_id,
                    created_by=metadata.created_by,
                )
                index_transport = SteamMemberPackageIndexTransport(client)
                index = index_transport.download(self.package_index_item_id)
                if not index.verify(
                    manifest,
                    expected_workshop_item_id=self.package_index_item_id,
                ):
                    raise CoordinationConfigurationError(
                        "This computer's Steam package index is not valid for the group."
                    )
                index_transport.update(index.add(artifact.remote_id, identity))
                return self._catalog_package(descriptor)

    def list_packages(self, project_uuid: str) -> list[CatalogPackage]:
        project_id = str(uuid.UUID(project_uuid))
        with self._client() as client:
            manifest, _identity = self._context(client)
            result = SteamGroupPackageDiscovery(client).discover(
                manifest,
                project_uuid=project_id,
            )
            self._log_rejections(result.rejected)
            return [self._catalog_package(item) for item in result.descriptors]

    def latest_package(self, project_uuid: str) -> CatalogPackage | None:
        project_id = str(uuid.UUID(project_uuid))
        with self._client() as client:
            manifest, _identity = self._context(client)
            result = SteamGroupPackageDiscovery(client).discover(
                manifest,
                project_uuid=project_id,
            )
            self._log_rejections(result.rejected)
            try:
                head = result.lineage(project_id).require_single_head()
            except SteamPackageForkError as error:
                raise PackageCatalogConflictError(str(error)) from error
            return self._catalog_package(head) if head is not None else None

    def list_latest_packages(self) -> list[CatalogPackage]:
        with self._client() as client:
            manifest, _identity = self._context(client)
            result = SteamGroupPackageDiscovery(client).discover(manifest)
            self._log_rejections(result.rejected)
            project_ids = sorted({item.project_uuid for item in result.descriptors})
            packages: list[CatalogPackage] = []
            for project_id in project_ids:
                try:
                    head = result.lineage(project_id).require_single_head()
                except SteamPackageForkError as error:
                    raise PackageCatalogConflictError(str(error)) from error
                if head is not None:
                    packages.append(self._catalog_package(head))
            return sorted(
                packages,
                key=lambda item: item.published_at_utc,
                reverse=True,
            )

    def remove_project(self, project_uuid: str) -> None:
        raise CoordinationConfigurationError(
            "Group-wide unsharing for Steam-native groups is not available yet."
        )

    @contextmanager
    def _client(self) -> Generator[SteamUgcClient, None, None]:
        bound = getattr(self._bound, "client", None)
        if bound is not None:
            yield bound
            return
        with self._lease_guard:
            hosting_client = next(
                (
                    state.client
                    for state in self._leases.values()
                    if state.client is not None
                ),
                None,
            )
        if hosting_client is not None:
            yield hosting_client
            return
        client = self.client_factory()
        try:
            yield client
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _close_client(client: SteamUgcClient) -> None:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    @classmethod
    def _dispose_state(cls, state: _LeaseState) -> None:
        if state.client is None:
            return
        try:
            if state.presence is not None:
                SteamHostingPresenceService(state.client).release(state.presence)
        except Exception as error:
            logger.warning(
                "Could not dispose Steam hosting lobby %s: %s",
                state.presence.lobby_id if state.presence is not None else "unknown",
                error,
            )
        finally:
            cls._close_client(state.client)

    def _context(
        self,
        client: SteamUgcClient,
    ) -> tuple[SteamGroupManifest, SteamDeviceIdentity]:
        steam_identity = client.current_identity()
        identity = self.identity_store.load_or_create(steam_identity.steam_id)
        if identity.device_id != self.device_id:
            raise CoordinationConfigurationError(
                "The saved Steam group belongs to a different device identity."
            )
        manifest = SteamGroupManifestTransport(
            client,
            cache=self.manifest_cache,
        ).download(
            self.manifest_item_id
        )
        if manifest.group_id != self.group_id:
            raise CoordinationConfigurationError(
                "The downloaded Steam manifest belongs to another group."
            )
        manifest.group_key_for(identity)
        reference = next(
            (
                item
                for item in manifest.member_package_indexes
                if item.device_id == identity.device_id
            ),
            None,
        )
        if (
            reference is None
            or reference.workshop_item_id != self.package_index_item_id
        ):
            raise CoordinationConfigurationError(
                "The Steam manifest does not contain this computer's package index."
            )
        return manifest, identity

    def _single_head_hash(
        self,
        client: SteamUgcClient,
        manifest: SteamGroupManifest,
        project_uuid: str,
    ) -> str:
        result = SteamGroupPackageDiscovery(client).discover(
            manifest,
            project_uuid=project_uuid,
        )
        self._log_rejections(result.rejected)
        try:
            head = result.lineage(project_uuid).require_single_head()
        except SteamPackageForkError as error:
            raise PackageCatalogConflictError(str(error)) from error
        return head.descriptor_hash if head is not None else ""

    def _owned_state(self, lease: LockLease) -> _LeaseState:
        state = self._leases.get(lease.project_uuid)
        if (
            state is None
            or state.lease.lease_id != lease.lease_id
            or state.lease.owner_device_id != self.device_id
            or state.lease.expired
        ):
            raise LockOwnershipError("This computer no longer owns the Steam lease.")
        return state

    def _key_id(self, epoch: int) -> str:
        return f"{_KEY_PREFIX}:{self.group_id}:{epoch}"

    def _key_epoch(self, key_id: str) -> int:
        prefix = f"{_KEY_PREFIX}:{self.group_id}:"
        if not key_id.startswith(prefix):
            raise CoordinationConfigurationError(
                "The package encryption key belongs to another Steam group."
            )
        try:
            epoch = int(key_id[len(prefix) :])
        except ValueError as error:
            raise CoordinationConfigurationError(
                "The Steam group key identifier is invalid."
            ) from error
        if epoch < 1:
            raise CoordinationConfigurationError(
                "The Steam group key epoch is invalid."
            )
        return epoch

    @staticmethod
    def _catalog_package(descriptor: SteamPackageDescriptor) -> CatalogPackage:
        return CatalogPackage(
            catalog_id=descriptor.version_id,
            artifact=PackageArtifact(
                transport_name="steam-ugc",
                remote_id=descriptor.workshop_item_id,
                project_uuid=descriptor.project_uuid,
                project_version=descriptor.project_version,
                package_checksum=descriptor.package_checksum,
                package_size_bytes=descriptor.package_size_bytes,
                encryption_key_id=(
                    f"{_KEY_PREFIX}:{descriptor.group_id}:{descriptor.key_epoch}"
                ),
            ),
            published_by_device_id=descriptor.publisher_device_id,
            published_at_utc=datetime.fromisoformat(descriptor.published_at_utc),
            metadata=PackageCatalogMetadata(
                project_name=descriptor.project_name,
                game_id=descriptor.game_id,
                created_by=descriptor.created_by,
            ),
        )

    @staticmethod
    def _item_id(value: str, label: str) -> str:
        normalized = str(value).strip()
        if not normalized.isdigit() or int(normalized) < 1:
            raise CoordinationConfigurationError(
                f"The Steam {label} item identifier is invalid."
            )
        return normalized

    @staticmethod
    def _log_rejections(rejected: Iterable[RejectedSteamPackage]) -> None:
        for item in rejected:
            logger.warning(
                "Rejected Steam group package item=%s owner=%s reason=%s",
                item.workshop_item_id,
                item.owner_steam_id,
                item.reason,
            )
