# Architecture

Save Shift is a Windows desktop application built with PySide6, SQLAlchemy, SQLite, PyInstaller, and Inno Setup. The code is organized around application workflows rather than direct UI access to storage or package internals.

## Runtime flow

`run_saveshift.py` calls `app.main.main()`. Startup initializes the SQLite schema, creates the Qt application, and opens `MainWindow`. A `.sspkg` path supplied through the Windows file association is passed to the window as a startup import. Normal launches may start a background update check after the UI is available.

## Layers

### UI (`app/ui`)

PySide6 windows, dialogs, cards, styles, and user interaction. UI handlers call services and present results; they do not implement package formats or save synchronization directly.

### Services (`app/services`)

Application workflows for installed games, projects, hosting, export, import, version history, World Journals, and restore. Services coordinate repositories, game implementations, package operations, checksums, and save-file operations.

### Games (`app/games`)

The game registry maps stable game IDs to implementations. Each supported game supplies metadata and discovery behavior for installed games, projects, and import targets. Game-specific paths stay outside generic import and hosting workflows.

### Packages (`app/packages`)

Creation, manifest serialization, reading, validation, extraction, and checksum support for `.sspkg` files. The version 1 manifest may include additive `journal_entries` metadata; older version 1 packages without that field remain readable. Stable journal-entry UUIDs make repeated handoffs idempotent. Package boundaries are intentionally mockable in service tests so workflow tests remain fast and deterministic.

### Persistence (`app/database`)

SQLAlchemy models and repositories backed by SQLite. Repositories own database queries; services own workflow rules. The production database defaults to `%USERPROFILE%\.saveshift\data\saveshift.sqlite3`.

Startup runs the versioned migration registry in `app/database/migrations` before repositories are used. SQLite `PRAGMA user_version` records the schema version without adding an application model. Fresh databases are created directly at the current version; unversioned alpha databases are identified by their known table and column shape. Before any schema-changing migration, SQLite's online backup API writes a consistent copy under `%USERPROFILE%\.saveshift\backups\database`. A failed migration restores that copy automatically. Databases from newer application versions and unknown or incomplete schemas are rejected instead of being modified speculatively.

Schema version 3 adds `session_journal_entries`. A journal entry belongs to a project, has a globally stable UUID for package deduplication, and may reference a project version number without becoming part of version lineage.

### Updates (`app/updates`)

The update service reads GitHub Releases, compares semantic versions, selects the versioned installer asset, downloads it, and validates available size and SHA-256 metadata. The controller runs network and download work away from the UI thread and launches the installer only after validation.

### Coordination (`app/coordination`)

The desktop coordinates project leases through a provider-neutral protocol and a versioned HTTPS adapter. Hosting retains and renews a lease until export or application exit. Import and restore use temporary leases. Project lock status is read in a background worker and refreshed on project cards without blocking the Qt UI. Every local destructive workflow also takes an operating-system file lock so concurrent Save Shift processes cannot mutate the same project simultaneously.

The first server implementation is isolated under `coordination/cloudflare/` and uses a Worker with one SQLite-backed Durable Object per group. Provisioning assigns a cryptographically random immutable group identity and uses it as the Durable Object name. Consequently, each group's devices, locks, encryption keys, and package catalog occupy separate storage even if an earlier group's Worker cleanup is delayed or fails. No Cloudflare dependency enters the Python application or PyInstaller build. The portable wire contract is defined in `coordination/openapi.yaml`; a future provider can implement it without changing desktop workflows.

The normal onboarding path uses single-use group invitations and administrator-managed devices. Cloudflare account provisioning is a separate adapter in `app/coordination/cloudflare_provisioning.py`: it uses browser OAuth with PKCE, uploads the bundled Worker, bootstraps the first administrator, and discards its temporary account access. The setup controller runs authorization, provisioning, invitation joins, departure, and owner-authorized Worker removal outside the Qt UI thread. Runtime lease operations never call Cloudflare's account API. The provider-neutral leave operation revokes the departing device and clears all Durable Object storage when the group becomes empty.

### Package transport

Remote package storage is separate from coordination and import. The
`PackageTransport` protocol publishes, downloads, and deletes immutable package
artifacts without exposing a provider SDK to application workflows.
`PackageTransferService` derives artifact identity from the verified `.sspkg`,
checks provider responses, downloads to a temporary sibling file, and validates
the package UUID, version, byte length, ZIP contents, and SHA-256 checksum before
atomically replacing the destination.

The package reader treats every received `.sspkg` as hostile even when its
sender is an authenticated group member. Version-1 archives must contain exactly
the regular files declared by the manifest, with matching checksums and safe,
case-unique relative paths. Links, special files, encrypted ZIP entries,
unsupported compression, Windows device or alternate-stream names, traversal,
and excessive member or expanded-byte counts are rejected before extraction.

`PackageHandoffService` composes the verified byte transport with the separate
coordination catalog. Publication requires the project's active lease, uploads
the immutable payload first, registers its descriptor second, and removes the
remote payload if catalog registration fails. Downloads select the newest
catalog entry and still pass through the complete transfer verification path.

Transport implementations may encode bytes internally, but they must return the
original `.sspkg` when downloading. `EncryptedPackageTransport` wraps an opaque
blob provider with streaming AES-256-GCM. Cloudflare stores only catalog metadata
and authenticated group encryption-key epochs; it never receives package bytes.
Removing a member rotates the key for future uploads, while retained historical
keys allow current members to recover earlier versions. An upload that races a
rotation is rejected by the catalog and retried once with the current key.

The first blob implementation uses unlisted Steam UGC under Save Shift AppID
5096900. `SteamUgcBlobTransport` owns the UGC folder layout and safe metadata,
while `SteamworksUgcClient` is a thin `ctypes` binding over the official flat API
and manual callback dispatcher. Steam holds only encrypted bytes and never
decides group membership or project lease ownership. The release build obtains
the redistributable `steam_api64.dll` from a local Steamworks SDK rather than
committing the proprietary SDK to the repository. Manual export and import
remain available as an offline fallback.

When coordination is configured, **Host** is the normal workflow. It acquires
the project lease, downloads and reconciles the group's latest encrypted
package, and only then launches the game. The desktop monitors the game process;
after a confirmed exit it creates and publishes the next version while the lease
is still held, then releases the lease only after the catalog accepts the
artifact. A failed publication keeps the lease for a safe manual retry. Users
can expose manual **Receive** and **Hand Off** controls in Settings for recovery
or troubleshooting. **Receive Shared World** remains available for the initial
addition of a project that is not yet tracked locally. Without coordination, the
same card positions retain manual Import and Export actions. Background
controllers keep Steam and network transfers off the Qt UI thread.

### Core (`app/core`)

Paths, settings, constants, logging, and other cross-cutting application configuration. `app/version.py` is the single source for application and Windows installer versions.

## Data safety

- Import backs up an existing project directory before synchronization.
- Restore creates a safety backup before replacing current files.
- Hosting, import, and restore take a cross-process local project lock.
- When remote coordination is enabled, write workflows fail closed if lease ownership cannot be confirmed.
- Device tokens are protected at rest with Windows Data Protection API and are never written to settings as plaintext.
- Package versions are checked to prevent duplicate or older imports.
- Checksums are recorded for imported and hosted versions.
- Schema-changing database migrations create a consistent backup first and automatically restore it if migration fails.
- Unknown, incomplete, and newer-than-supported database schemas fail closed before repositories are used.
- Pytest sets `SAVESHIFT_DATABASE_PATH` before importing database code, and database initialization refuses to run under pytest without an explicit override.
- Filesystem and package boundaries are mocked where isolation matters; repositories use the temporary real SQLite database where meaningful.

## Packaging and releases

`tools/build_release.ps1` runs Python and Cloudflare tests, regenerates the bundled coordination Worker, locates the official Steamworks Windows redistributable through `STEAMWORKS_SDK_PATH`, builds `SaveShift.spec` with PyInstaller, reads version values from `app/version.py`, and invokes `installer/SaveShift.iss`. GitHub prereleases publish the resulting versioned installer. The updater requires the asset name to match `SaveShiftSetup-<version>.exe`.

## Architectural decisions

- [ADR-0001: Package format](decisions/ADR-0001-package-format.md)
- [ADR-0002: Fork behavior](decisions/ADR-0002-fork-behavior.md)
- [ADR-0003: Provider-neutral project coordination](decisions/ADR-0003-provider-neutral-coordination.md)
- [ADR-0004: Cloudflare OAuth provider provisioning](decisions/ADR-0004-cloudflare-oauth-provisioning.md)
- [ADR-0005: Embedded database migrations](decisions/ADR-0005-embedded-database-migrations.md)
- [ADR-0006: Provider-neutral package transport](decisions/ADR-0006-provider-neutral-package-transport.md)
