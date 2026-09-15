# ADR-0008: Steam Group Recovery

## Status

Accepted

## Context

A Steam-native group depends on an administrator device identity and a stable,
administrator-owned Workshop manifest. Losing the only copy of that private
identity would prevent membership changes and key rotation even though package
data still exists on Steam. A temporary Steam outage should also not erase the
last verified description of the group.

The local cache cannot become a coordination fallback. It can be stale, and
using it to decide the current package head, membership, or hosting state would
reintroduce silent forks and revoked-member access.

## Decision

- Save Shift caches every successfully published, updated, or downloaded group
  manifest only after verifying its administrator signature. The cache records
  the pinned Workshop item identifier and is used for recovery and diagnostics,
  not live coordination.
- A group administrator can export a `.ssrecovery` file. The private signing
  key, private agreement key, manifest, administrator package-index coordinate,
  and manifest coordinate are authenticated and encrypted with AES-256-GCM.
  The encryption key is derived from a password of at least 12 characters using
  scrypt with a unique random salt.
- Import requires the same signed-in Steam account as the administrator. It
  verifies the embedded manifest signature, reconstructed public identity,
  encrypted group-key envelope, and pinned coordinates before persisting any
  recovered state.
- Replacing an existing, different device identity requires an explicit warning
  because that identity may still grant access to other groups on the computer.
- After recovery, ordinary operations must download and verify the live Steam
  manifest before making coordination or package-head decisions.

## Deferred administrator transfer

Steam Workshop ownership cannot be reassigned. A safe administrator transfer
therefore needs a successor manifest owned by the new administrator plus a
signed redirect from the old manifest, with both sides verified before local
settings switch. Save Shift will not present a transfer button until that
two-party protocol, replica discovery, and interruption tests are implemented.

## Consequences

- An administrator can recover a group after replacing a computer without
  giving Steam or another service plaintext access to group keys.
- Anyone who obtains both the recovery file and its password can administer the
  group and decrypt its saves, so the UI instructs users to store them
  separately.
- Recovery preserves the same logical device identity; it does not create a new
  member or weaken manifest signature verification.
- Cached state improves recovery and diagnosis but never permits offline shared
  hosting or publication.
