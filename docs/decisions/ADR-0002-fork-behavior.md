# ADR-0002: Project Fork Behavior

## Status

Accepted

## Context

Projects may be forked after any version. Steam-native groups also need a safe,
explicit response when someone chooses to play without the online group state
that normally acts as the hosting lock.

## Decision

Forking creates a new Project and copies the version history up to the selected version.

Future versions are independent.

Choosing **Play Offline as a Fork** for a shared project follows the same rule:
Save Shift creates a separate local Project identity before launching the game.
The original shared project and group head remain unchanged. The offline fork is
never handed back to the group automatically; merging or replacing the group
head requires an explicit conflict-recovery flow after reconnecting.

## Consequences

- Simple deletion semantics.
- No shared history between projects.
- Slight duplication of metadata.
- Offline play cannot accidentally masquerade as ownership of the synchronized
  group world.
- Connectivity lost during a legitimate online host session is retained as a
  pending branch until Save Shift can compare it with the group head.
