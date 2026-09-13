from dataclasses import dataclass

from app.steam.package_descriptor import SteamPackageDescriptor


class SteamPackageForkError(ValueError):
    pass


@dataclass(frozen=True)
class SteamPackageLineage:
    project_uuid: str
    descriptors: tuple[SteamPackageDescriptor, ...]
    heads: tuple[SteamPackageDescriptor, ...]
    fork_parent_hashes: tuple[str, ...]
    missing_parent_hashes: tuple[str, ...]

    @property
    def forked(self) -> bool:
        return bool(self.fork_parent_hashes) or len(self.heads) > 1

    @property
    def incomplete(self) -> bool:
        return bool(self.missing_parent_hashes)

    def require_single_head(self) -> SteamPackageDescriptor | None:
        if self.forked:
            raise SteamPackageForkError(
                "This shared world has competing Steam package branches."
            )
        if self.incomplete:
            raise SteamPackageForkError(
                "This shared world's Steam package history is incomplete."
            )
        return self.heads[0] if self.heads else None

    @classmethod
    def resolve(
        cls,
        project_uuid: str,
        descriptors: list[SteamPackageDescriptor]
        | tuple[SteamPackageDescriptor, ...],
    ) -> "SteamPackageLineage":
        relevant = [
            descriptor
            for descriptor in descriptors
            if descriptor.project_uuid == project_uuid
        ]
        by_hash: dict[str, SteamPackageDescriptor] = {}
        version_ids: dict[str, str] = {}
        for descriptor in relevant:
            descriptor_hash = descriptor.descriptor_hash
            existing_hash = version_ids.get(descriptor.version_id)
            if existing_hash is not None and existing_hash != descriptor_hash:
                raise ValueError("A Steam package version ID identifies two packages.")
            version_ids[descriptor.version_id] = descriptor_hash
            by_hash[descriptor_hash] = descriptor

        child_hashes: dict[str, list[str]] = {}
        for descriptor_hash, descriptor in by_hash.items():
            if descriptor.parent_descriptor_hash:
                child_hashes.setdefault(descriptor.parent_descriptor_hash, []).append(
                    descriptor_hash
                )

        referenced = {
            descriptor.parent_descriptor_hash
            for descriptor in by_hash.values()
            if descriptor.parent_descriptor_hash in by_hash
        }
        heads = tuple(
            sorted(
                (
                    descriptor
                    for descriptor_hash, descriptor in by_hash.items()
                    if descriptor_hash not in referenced
                ),
                key=lambda item: (item.published_at_utc, item.descriptor_hash),
            )
        )
        forks = tuple(
            sorted(
                parent_hash
                for parent_hash, children in child_hashes.items()
                if len(set(children)) > 1
            )
        )
        missing = tuple(
            sorted(
                parent_hash
                for parent_hash in child_hashes
                if parent_hash not in by_hash
            )
        )
        return cls(
            project_uuid=project_uuid,
            descriptors=tuple(
                sorted(by_hash.values(), key=lambda item: item.descriptor_hash)
            ),
            heads=heads,
            fork_parent_hashes=forks,
            missing_parent_hashes=missing,
        )
