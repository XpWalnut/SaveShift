# ADR-0007: Steam-Native Groups and Coordination

## Status

Accepted

## Context

Save Shift currently uses Steam UGC for encrypted package bytes and a
per-group Cloudflare Durable Object for membership, invitations, package
discovery, encryption-key epochs, and exclusive host leases. Requiring each
group owner to authorize and operate a third-party Worker makes onboarding and
support substantially more complex than the desktop workflow itself.

Steam provides authenticated identities, friend relationships, lobby invites,
lobby messages, and persistent UGC. A private Steam lobby can therefore perform
an authenticated invitation ceremony without copying a token through another
application. It cannot be the durable group database: Steam destroys a lobby
after its final member leaves, and a user cannot remain in an arbitrary number
of regular lobbies.

Steam also does not expose a durable, group-scoped compare-and-swap primitive.
Without an always-online coordinator, two disconnected members can both start
from the same package and produce competing successors. A Steam-only design
must detect and present that fork rather than claim to provide a strict global
lock.

Workshop visibility is not a group access-control mechanism. Friends-only
items are visible to all friends of their publisher, while unlisted items are
accessible to anyone who obtains the identifier. Package confidentiality must
continue to come from Save Shift encryption.

## Decision

Save Shift will work toward a Steam-native coordination provider while keeping
the current provider protocols and Cloudflare implementation available during
migration.

### Identity and invitations

- Each Save Shift installation creates an Ed25519 signing key and an X25519 key
  agreement key. Private keys are protected locally with the operating
  system's credential protection; only public keys leave the device.
- A group has a random identifier, an administrator signing identity, and a
  random 256-bit package key for each encryption epoch.
- Creating or joining a group uses a temporary private Steam lobby. The owner
  opens Steam's friend-invite overlay, and Steam authenticates the invited
  account when it enters the lobby.
- The joining device sends its public keys through the lobby. The administrator
  returns a signed membership certificate, the current group manifest
  identifier, and the current package key encrypted specifically to the new
  device's X25519 public key.
- The invitation lobby is transport for the ceremony only. Both computers
  persist the accepted group locally before leaving it.

### Persistent group state

- The group administrator owns one stable Workshop manifest item. Its opaque
  payload contains the signed group name, administrator identity, membership
  certificates, member Steam IDs and public keys, revoked certificate IDs,
  current key epoch, and one encrypted key envelope per active member.
- Members know the manifest item ID from their invitation and can refresh it
  directly. Signatures prevent a downloaded or locally modified manifest from
  impersonating the administrator.
- Removing a member creates a new package-key epoch and new envelopes for the
  remaining members. As today, revocation cannot erase keys or save bytes that
  a formerly authorized member already copied.

### Save publication and discovery

- Every package remains authenticated and encrypted before Steam receives it.
- A package contains a signed descriptor with the group ID, world UUID,
  version ID, parent descriptor hash, publisher Steam ID, publisher device key,
  timestamp, encrypted payload checksum, and Workshop item ID.
- Each member publishes packages under their own Steam account and maintains one
  stable, signed package-index item whose ID is pinned into the group manifest.
  Group members follow those indexes to unlisted package items and reject
  descriptors without a valid active membership signature.
- Local history stores all accepted descriptor heads. The normal path advances
  from exactly one known parent; packages with the same parent form an explicit
  fork and require recovery rather than silently choosing the largest version
  number.
- Package discovery does not depend on querying a member's Workshop list: Steam
  does not return another user's unlisted items there unless the caller is already
  subscribed. Direct item downloads preserve unlisted visibility and first-use
  discovery.

### Hosting semantics

- While members are online, a short-lived per-world Steam lobby advertises the
  active host and improves the normal user experience by preventing an obvious
  second launch.
- The lobby is advisory, not a durable lease. Before launching, Save Shift
  refreshes the manifest and package heads. Before publishing, it refreshes
  them again and refuses an automatic handoff if another valid child of the
  starting head exists.
- The UI will say **Available**, **Hosted by ...**, **Offline status unknown**,
  or **Fork needs attention** instead of implying a lock that Steam cannot
  guarantee.
- Hosting a shared world requires a Steam connection by default. A user may
  explicitly choose **Play Offline as a Fork**, which creates a new local
  project identity before launch and never publishes back into the group
  automatically.
- Losing Steam connectivity during an already-running hosted session does not
  discard the player's work. Save Shift packages it locally, marks it as a
  pending branch, and reconciles it against the refreshed group head after
  connectivity returns.

## Migration

1. Add Steam identity, friends, matchmaking, lobby-callback, and UGC-query
   bindings behind testable protocols.
2. Implement local device keys, signed membership certificates, and manifest
   serialization without changing existing groups.
3. Add Steam-lobby friend invitations and create Steam-native test groups.
4. Implement signed package descriptors, member UGC discovery, and fork tests.
5. Run Cloudflare and Steam-native providers side by side behind a per-group
   provider type. Existing Cloudflare groups continue to work unchanged.
6. After multi-PC testing, make Steam-native groups the default and offer an
   explicit migration flow. Remove Cloudflare from release packaging only after
   migrated groups have verified matching heads and recovery backups.

## Consequences

- New users no longer need a Cloudflare account, browser authorization, domain,
  Worker deployment, or third-party service configuration.
- Invitations use the familiar Steam friend interface and are bound to the
  authenticated Steam accounts that accepted them.
- Group membership and package contents remain end-to-end protected from
  unrelated Steam users who can see or guess a Workshop item.
- Strict offline mutual exclusion is replaced by an online-only synchronized
  workflow and explicit local forks. This limitation must be visible in the
  product and tests; offline play is never presented as synchronized hosting.
- The group administrator remains necessary for membership changes and key
  rotation. Losing every administrator private key requires a documented group
  recovery or recreation process.
- Steam-native groups require every participant to own and run Save Shift
  through Steam. Manual package export/import remains the non-Steam fallback.
