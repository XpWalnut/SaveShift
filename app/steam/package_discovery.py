from dataclasses import dataclass

from app.steam.group_manifest import SteamGroupManifest
from app.steam.package_descriptor import SteamPackageDescriptor
from app.steam.package_descriptor_transport import SteamPackageDescriptorTransport
from app.steam.package_index import SteamMemberPackageIndex
from app.steam.package_index_transport import SteamMemberPackageIndexTransport
from app.steam.package_lineage import SteamPackageLineage
from app.steam.ugc_client import SteamUgcClient


@dataclass(frozen=True)
class RejectedSteamPackage:
    workshop_item_id: str
    owner_steam_id: str
    reason: str


@dataclass(frozen=True)
class SteamPackageDiscoveryResult:
    descriptors: tuple[SteamPackageDescriptor, ...]
    rejected: tuple[RejectedSteamPackage, ...]

    def lineage(self, project_uuid: str) -> SteamPackageLineage:
        return SteamPackageLineage.resolve(project_uuid, self.descriptors)


class SteamGroupPackageDiscovery:
    """Discovers unlisted packages through signed, manifest-pinned member indexes."""

    def __init__(self, client: SteamUgcClient) -> None:
        self.client = client

    def discover(
        self,
        manifest: SteamGroupManifest,
        *,
        project_uuid: str | None = None,
    ) -> SteamPackageDiscoveryResult:
        if not manifest.verify():
            raise ValueError("The Steam group manifest signature is invalid.")
        accepted: dict[str, SteamPackageDescriptor] = {}
        rejected: list[RejectedSteamPackage] = []
        indexes = SteamMemberPackageIndexTransport(self.client)
        descriptors = SteamPackageDescriptorTransport(self.client)
        for reference in manifest.member_package_indexes:
            try:
                index = indexes.download(reference.workshop_item_id)
                if not index.verify(
                    manifest,
                    expected_workshop_item_id=reference.workshop_item_id,
                ):
                    raise ValueError("The member package index signature is invalid.")
            except ValueError as error:
                rejected.append(
                    RejectedSteamPackage(
                        reference.workshop_item_id,
                        reference.steam_id,
                        str(error),
                    )
                )
                continue
            for item_id in index.package_item_ids:
                try:
                    descriptor = descriptors.read(item_id)
                except ValueError as error:
                    rejected.append(
                        RejectedSteamPackage(item_id, reference.steam_id, str(error))
                    )
                    continue
                reason = self._rejection_reason(
                    descriptor,
                    index,
                    manifest,
                    item_id,
                )
                if reason is not None:
                    rejected.append(
                        RejectedSteamPackage(item_id, reference.steam_id, reason)
                    )
                elif project_uuid is None or descriptor.project_uuid == project_uuid:
                    accepted[descriptor.descriptor_hash] = descriptor
        # A compaction checkpoint is manifest-pinned rather than member-index-pinned.
        # This lets the administrator publish a replacement chain atomically before
        # asking individual members to prune the indexes they personally own.
        for checkpoint in manifest.retention_checkpoints:
            if project_uuid is not None and checkpoint.project_uuid != project_uuid:
                continue
            for item_id in checkpoint.package_item_ids:
                try:
                    descriptor = descriptors.read(item_id)
                except ValueError as error:
                    rejected.append(
                        RejectedSteamPackage(
                            item_id, manifest.administrator_steam_id, str(error)
                        )
                    )
                    continue
                if not descriptor.verify(manifest, expected_workshop_item_id=item_id):
                    rejected.append(
                        RejectedSteamPackage(
                            item_id,
                            manifest.administrator_steam_id,
                            "The retention checkpoint descriptor signature is invalid.",
                        )
                    )
                elif descriptor.project_uuid != checkpoint.project_uuid:
                    rejected.append(
                        RejectedSteamPackage(
                            item_id,
                            manifest.administrator_steam_id,
                            "The retention checkpoint references another world.",
                        )
                    )
                else:
                    accepted[descriptor.descriptor_hash] = descriptor
        accepted = self._filter_compacted_histories(accepted, manifest)
        return SteamPackageDiscoveryResult(
            descriptors=tuple(
                sorted(accepted.values(), key=lambda value: value.descriptor_hash)
            ),
            rejected=tuple(rejected),
        )

    @staticmethod
    def _filter_compacted_histories(
        accepted: dict[str, SteamPackageDescriptor],
        manifest: SteamGroupManifest,
    ) -> dict[str, SteamPackageDescriptor]:
        """Ignore predecessors which were superseded by a signed checkpoint."""
        retained = dict(accepted)
        for checkpoint in manifest.retention_checkpoints:
            by_hash = {
                item.descriptor_hash: item
                for item in retained.values()
                if item.project_uuid == checkpoint.project_uuid
            }
            root = by_hash.get(checkpoint.root_descriptor_hash)
            if root is None or root.parent_descriptor_hash:
                # The later lineage check reports this as incomplete.  Do not silently
                # fall back to an intentionally superseded history.
                continue
            allowed: set[str] = set()
            for descriptor_hash, descriptor in by_hash.items():
                cursor = descriptor
                seen: set[str] = set()
                while True:
                    current_hash = cursor.descriptor_hash
                    if current_hash in seen:
                        break
                    seen.add(current_hash)
                    if current_hash == checkpoint.root_descriptor_hash:
                        allowed.add(descriptor_hash)
                        break
                    if not cursor.parent_descriptor_hash:
                        break
                    parent = by_hash.get(cursor.parent_descriptor_hash)
                    if parent is None:
                        break
                    cursor = parent
            for descriptor_hash, descriptor in tuple(retained.items()):
                if (
                    descriptor.project_uuid == checkpoint.project_uuid
                    and descriptor_hash not in allowed
                ):
                    retained.pop(descriptor_hash)
        return retained

    @staticmethod
    def _rejection_reason(
        descriptor: SteamPackageDescriptor,
        index: SteamMemberPackageIndex,
        manifest: SteamGroupManifest,
        item_id: str,
    ) -> str | None:
        if (
            descriptor.publisher_steam_id != index.publisher_steam_id
            or descriptor.publisher_device_id != index.publisher_device_id
        ):
            return "The package was not signed by its package-index publisher."
        if not descriptor.verify(
            manifest,
            expected_workshop_item_id=item_id,
        ):
            return "The package descriptor signature or membership is invalid."
        return None
