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
        return SteamPackageDiscoveryResult(
            descriptors=tuple(
                sorted(accepted.values(), key=lambda value: value.descriptor_hash)
            ),
            rejected=tuple(rejected),
        )

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
