# Changelog

All notable changes to Save Shift are documented here. The project is currently in alpha, so package and database compatibility may change before the first stable release.

## [Unreleased]

### Added

- New neon pixel-art branding assets for the Windows application icon and
  Steamworks banner artwork.
- An optional World Journal prompt for completed hosted sessions, including a
  persistent "don't ask again" choice and a matching Settings toggle.
- A Shared Projects group inbox that discovers the newest Steam handoff for
  projects not yet tracked on a computer and imports them through the existing
  conflict, backup, and game-discovery workflow.
- Friendly project name, game, and creator metadata in provider-neutral package
  catalog records, with backward-compatible handling of older records.
- A provider-neutral package transport contract with verified publication,
  atomic downloads, provider matching, integrity failure cleanup, and an
  end-to-end transport/import regression test.
- A provider-neutral package catalog in the coordination API, including
  lease-authorized publication, idempotent registration, collision detection,
  and newest-version discovery.
- Streaming AES-256-GCM package encryption with authenticated group key epochs,
  future-key rotation after membership removal, historical-key recovery for
  current members, and one safe retry when rotation races publication.
- Package handoff orchestration that composes encrypted blob storage with the
  metadata catalog and removes orphaned uploads when registration fails.
- Save Shift Steam AppID 5096900 integration through the official Steamworks
  flat API, with manual callback dispatch, descriptive initialization errors,
  and release packaging of the Windows redistributable.
- An unlisted Steam UGC blob adapter with safe package metadata, Workshop
  agreement notification, cached-download retrieval, failed-upload cleanup,
  and deletion support.
- Coordinated **Receive** and **Hand Off** project-card workflows that perform
  Steam transfers off the UI thread, reuse import conflict handling and backups,
  and release the project lease only after a successful cataloged upload.
- Steam download recovery that tolerates transient callback failures while the
  Steam client continues installing a Workshop item in the background.
- Added a one-command SteamPipe upload script with release-build validation,
  generated credential-free configuration, and a non-networked dry-run mode.
- Import previews that distinguish verified continuations, unverified or
  divergent histories, duplicates, older packages, and version collisions.
- Explicit backup-and-replace acknowledgement for imports whose ancestry
  cannot be safely verified.
- Backward-compatible package metadata for source devices, timeline ancestry,
  notes, and safe game-specific details.
- Schedule I save-folder detection, project discovery, import targeting, and Steam launching.
- User-initiated Steam scanning across the primary and secondary library folders.
- Optional cross-device project leases for hosting, import, export, and restore workflows.
- Provider-neutral `/api/v1` coordination contract and Python HTTP adapter.
- Self-deployable Cloudflare Worker and SQLite-backed Durable Object adapter.
- Cross-process operating-system locks for destructive local save operations.
- Settings controls for provider URL, device pairing, and coordination opt-in.
- Project-card lock status showing owner, local ownership, and lease expiration.
- Persistent profile name used for history and coordination attribution.
- Windows DPAPI protection for stored device credentials.
- Python regression tests and Cloudflare contract tests for lock behavior.
- Browser-based Cloudflare OAuth provisioning with PKCE and temporary account access.
- Create Group and Join Group settings workflows.
- Short-lived, single-use group invitations.
- Group computer listing and administrator revocation.
- One-time administrator migration for providers deployed by earlier alphas.
- A release-bundled coordination Worker generated and verified during builds.
- Group departure, legacy local disconnect, final-device storage cleanup, and owner-authorized Cloudflare Worker deletion.
- Versioned SQLite schema migrations with legacy alpha schema detection.
- Automatic pre-migration database backups and failure restoration.
- Regression coverage for fresh, legacy, incomplete, current, and newer database schemas.
- Optional World Journal entries with author, timestamp, title, body, and version association.
- Latest journal-entry previews on project cards and a full World Journal tab in project history.
- Additive journal metadata in `.sspkg` files with stable UUID-based import deduplication and backward compatibility for existing packages.
- Schema version 3 and migration coverage for persisted journal entries.
- Service, package, integration, and UI regression coverage for journal workflows.

### Changed

- Hosting retains and renews its project lease until export or application exit.
- Import and restore fail before touching save files when a remote lock cannot be verified.
- Host, import, export, and restore reuse the saved profile name instead of prompting for every operation.
- Raw provider URL and reusable pairing-code controls now live under Advanced setup.

## [0.1.0-alpha.3] - 2026-07-13

### Added

- Automatic and manual update checks backed by GitHub Releases.
- Installer download progress, size validation, SHA-256 validation, and installer launch flow.
- Settings UI for enabling or disabling automatic update checks.
- Regression coverage for game discovery, hosting, package import/export, project history, restore, settings, updates, and UI workflows.
- Integration coverage for package handoff workflows.

### Changed

- Release builds now run the complete pytest suite before packaging.
- Application and installer versions now share a central version source.
- Installed-game cards reserve space for the vertical scrollbar.

### Fixed

- Tests are prevented from connecting to the real user database.
- Regression fixtures no longer leave test games in production data.

## [0.1.0-alpha.2] - 2026-07-10

### Fixed

- Import button behavior.
- Windows release build configuration.

## [0.1.0-alpha.1] - 2026-07-10

### Added

- Initial Windows alpha release.
- Automatic installed-game and project discovery.
- Support for Abiotic Factor, Valheim, and V Rising.
- Hosting, Steam launch, `.sspkg` import/export, history, and restore workflows.
- Windows installer and `.sspkg` file association.

[0.1.0-alpha.3]: https://github.com/XpWalnut/SaveShift/releases/tag/v0.1.0-alpha.3
[0.1.0-alpha.2]: https://github.com/XpWalnut/SaveShift/releases/tag/v0.1.0-alpha.2
[0.1.0-alpha.1]: https://github.com/XpWalnut/SaveShift/releases/tag/v0.1.0-alpha.1
