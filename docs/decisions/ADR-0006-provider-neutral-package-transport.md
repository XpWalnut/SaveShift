# ADR-0006: Provider-Neutral Package Transport

## Status

Accepted

## Context

Save Shift already creates verified `.sspkg` files and coordinates exclusive
project operations through a provider-neutral locking API. The normal group
handoff still requires users to move packages manually. Steam UGC is the planned
first remote file transport, but Steam storage must not become a dependency of
package creation, import conflict handling, or Cloudflare lease management.

Steam UGC visibility does not directly represent Save Shift group membership.
An unlisted item is undiscoverable through global queries but is not private to
a Save Shift group. The Steam adapter must therefore treat confidentiality as
an application concern rather than relying on item visibility alone.

## Decision

Save Shift defines a `PackageTransport` protocol for publishing, downloading,
and deleting immutable package artifacts. A `PackageArtifact` contains the
stable transport name and remote identifier alongside the project UUID,
project version, original package size, and original package SHA-256 checksum.

`PackageTransferService` owns provider-independent verification:

- A package is fully parsed and verified before publication.
- The provider must return the descriptor it was given without changing its
  identity or integrity metadata.
- Downloads are written to a unique temporary sibling path.
- Size, checksum, package structure, project UUID, and project version are
  checked before the requested destination is atomically replaced.
- A failed download removes its partial file and preserves an existing
  destination.
- An artifact may only be used with the transport provider that created it.

A provider may encode or encrypt bytes internally, but downloading must produce
the original verified `.sspkg`. The Steam implementation will encrypt packages
before they are uploaded as unlisted UGC. Retrieval metadata and access to the
encryption material will be limited to authenticated group members through the
coordination layer.

The coordination API contains a small package catalog, not a file store. A
catalog record contains the immutable artifact descriptor, publisher, timestamp,
and encryption-key epoch. Registering a record requires an active project lease.
The group Durable Object also creates AES-256-GCM key epochs and exposes them only
to authenticated devices. Membership removal invalidates the current epoch so
future publications use a new key; historical epochs remain readable by current
members so old versions can still be restored. If key rotation races a publish,
the catalog rejects the stale epoch and the handoff retries once.

`EncryptedPackageTransport` performs streaming authenticated encryption around
an opaque blob provider. This keeps encryption independent of Steam and means a
future storage provider can replace Steam without receiving plaintext package
files. The coordination provider necessarily knows the group keys in this
self-hosted design; the boundary protects unlisted storage objects from outsiders
rather than claiming zero-knowledge encryption from the group's provider.

Package transport and coordination remain separate abstractions. Cloudflare
does not carry package bytes, and the Steam adapter does not decide whether a
device owns a project lease.

## Consequences

- A different storage provider can replace Steam without changing package or
  import workflows.
- Transport corruption or an incorrect provider response is detected before an
  existing local package is replaced.
- Steam-specific SDK initialization, manual callbacks, UGC identifiers, and
  legal-agreement handling stay inside `app/steam`; encryption remains a
  provider-neutral transport wrapper.
- Cloudflare stores strongly consistent package metadata and key epochs in the
  existing group Durable Object, but never stores package bytes.
- Revocation prevents a former member from obtaining future keys. It cannot
  revoke package bytes or keys that member already copied while authorized.
- Retention policy remains a separate concern from the catalog contract.
- Manual `.sspkg` export and import remain supported as an offline fallback.
