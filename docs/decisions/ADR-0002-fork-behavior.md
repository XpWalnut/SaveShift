# ADR-0002: Project Fork Behavior

## Status

Accepted

## Context

Projects may be forked after any version.

## Decision

Forking creates a new Project and copies the version history up to the selected version.

Future versions are independent.

## Consequences

- Simple deletion semantics.
- No shared history between projects.
- Slight duplication of metadata.