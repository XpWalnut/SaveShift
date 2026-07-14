# ADR-0003: Provider-Neutral Project Coordination

## Status

Accepted

## Context

Save Shift needs cross-device project locks to reduce simultaneous hosting and destructive save conflicts. The first coordination provider will use Cloudflare Workers and Durable Objects because their free tier offers strongly consistent, transactional state suitable for leases.

Cloudflare is an implementation choice, not a permanent architectural dependency. The desktop application must remain portable to a self-hosted service or another serverless provider without changing hosting, import, export, or restore rules.

## Decision

The desktop depends on a Python `CoordinationProvider` protocol containing only provider-neutral operations:

- Pair a device.
- Acquire a project lease.
- Renew an owned lease.
- Release an owned lease.
- Read current project lock status.

All remote providers implement the versioned `/api/v1` HTTP contract in [`coordination/openapi.yaml`](../../coordination/openapi.yaml). Requests and responses use provider-neutral JSON models. Provider-specific deployment code, bindings, storage APIs, and dependencies live outside the desktop application.

Every lease contains a monotonically increasing fencing token. Lease IDs prove ownership for renewal and release; device credentials authenticate the caller. Expired leases may be replaced atomically.

Local filesystem mutation is additionally protected by an operating-system file lock. Local locking is independent from remote coordination and automatically releases if a process exits.

The first hosted adapter lives under `coordination/cloudflare/`. The desktop HTTP adapter has no Cloudflare imports and accepts any valid HTTPS base URL implementing the contract.

Coordination deliberately does not upload or download save packages. A future cloud or Steam Workshop integration belongs behind a separate package-transport contract. Storage transport and lock ownership may evolve independently, and a file transport must not be treated as an atomic locking mechanism unless it explicitly provides compare-and-set lease semantics.

## Consequences

- Replacing Cloudflare requires a new server implementation of the existing HTTP contract, not changes to desktop workflows.
- Contract tests can be run against every provider implementation.
- Cloudflare types and packages never enter the PyInstaller dependency graph.
- Coordination can be disabled without disabling local operation locks.
- API evolution must remain backward compatible within `/api/v1` or introduce a new version.
- Remote coordination depends on network availability, so UI workflows must report unavailable and conflicting states explicitly.
