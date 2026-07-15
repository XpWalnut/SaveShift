# Architecture

Save Shift is a Windows desktop application built with PySide6, SQLAlchemy, SQLite, PyInstaller, and Inno Setup. The code is organized around application workflows rather than direct UI access to storage or package internals.

## Runtime flow

`run_saveshift.py` calls `app.main.main()`. Startup initializes the SQLite schema, creates the Qt application, and opens `MainWindow`. A `.sspkg` path supplied through the Windows file association is passed to the window as a startup import. Normal launches may start a background update check after the UI is available.

## Layers

### UI (`app/ui`)

PySide6 windows, dialogs, cards, styles, and user interaction. UI handlers call services and present results; they do not implement package formats or save synchronization directly.

### Services (`app/services`)

Application workflows for installed games, projects, hosting, export, import, history, and restore. Services coordinate repositories, game implementations, package operations, checksums, and save-file operations.

### Games (`app/games`)

The game registry maps stable game IDs to implementations. Each supported game supplies metadata and discovery behavior for installed games, projects, and import targets. Game-specific paths stay outside generic import and hosting workflows.

### Packages (`app/packages`)

Creation, manifest serialization, reading, validation, extraction, and checksum support for `.sspkg` files. Package boundaries are intentionally mockable in service tests so workflow tests remain fast and deterministic.

### Persistence (`app/database`)

SQLAlchemy models and repositories backed by SQLite. Repositories own database queries; services own workflow rules. The production database defaults to `%USERPROFILE%\.saveshift\data\saveshift.sqlite3`.

### Updates (`app/updates`)

The update service reads GitHub Releases, compares semantic versions, selects the versioned installer asset, downloads it, and validates available size and SHA-256 metadata. The controller runs network and download work away from the UI thread and launches the installer only after validation.

### Coordination (`app/coordination`)

The desktop coordinates project leases through a provider-neutral protocol and a versioned HTTPS adapter. Hosting retains and renews a lease until export or application exit. Import and restore use temporary leases. Project lock status is read in a background worker and refreshed on project cards without blocking the Qt UI. Every local destructive workflow also takes an operating-system file lock so concurrent Save Shift processes cannot mutate the same project simultaneously.

The first server implementation is isolated under `coordination/cloudflare/` and uses a Worker with a SQLite-backed Durable Object. No Cloudflare dependency enters the Python application or PyInstaller build. The portable wire contract is defined in `coordination/openapi.yaml`; a future provider can implement it without changing desktop workflows.

The normal onboarding path uses single-use group invitations and administrator-managed devices. Cloudflare account provisioning is a separate adapter in `app/coordination/cloudflare_provisioning.py`: it uses browser OAuth with PKCE, uploads the bundled Worker, bootstraps the first administrator, and discards its temporary account access. The setup controller runs authorization, provisioning, invitation joins, departure, and owner-authorized Worker removal outside the Qt UI thread. Runtime lease operations never call Cloudflare's account API. The provider-neutral leave operation revokes the departing device and clears all Durable Object storage when the group becomes empty.

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
- Pytest sets `SAVESHIFT_DATABASE_PATH` before importing database code, and database initialization refuses to run under pytest without an explicit override.
- Filesystem and package boundaries are mocked where isolation matters; repositories use the temporary real SQLite database where meaningful.

## Packaging and releases

`tools/build_release.ps1` runs Python and Cloudflare tests, regenerates the bundled coordination Worker, builds `SaveShift.spec` with PyInstaller, reads version values from `app/version.py`, and invokes `installer/SaveShift.iss`. GitHub prereleases publish the resulting versioned installer. The updater requires the asset name to match `SaveShiftSetup-<version>.exe`.

## Architectural decisions

- [ADR-0001: Package format](decisions/ADR-0001-package-format.md)
- [ADR-0002: Fork behavior](decisions/ADR-0002-fork-behavior.md)
- [ADR-0003: Provider-neutral project coordination](decisions/ADR-0003-provider-neutral-coordination.md)
- [ADR-0004: Cloudflare OAuth provider provisioning](decisions/ADR-0004-cloudflare-oauth-provisioning.md)
