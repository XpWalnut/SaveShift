# Changelog

All notable changes to Save Shift are documented here. The project is currently in alpha, so package and database compatibility may change before the first stable release.

## [Unreleased]

### Added

- Side-by-side Cloudflare and Steam-native coordination selected per group.
  Steam-native groups now encrypt with manifest key epochs, publish signed
  ancestry descriptors through stable member-owned indexes, discover the one
  valid group head, and stop a handoff when another member advanced the head
  after hosting began. Existing Cloudflare groups retain their current provider
  and behavior.
- A guarded schema-4-to-schema-3 database downgrade tool for temporarily
  returning to the `develop` build, with a verified backup and automatic restore
  on failure.
- Steam-native group foundations: authenticated friend-list invitation lobbies,
  signed per-device membership certificates, a stable signed Workshop manifest,
  per-member encrypted group-key envelopes, revocation key rotation, and
  authenticated lobby enrollment without exposing private keys.
- The Create Group, Join Group, and Invite a Friend screens now drive Steam's
  signed manifest and friend-lobby enrollment flow for new groups, while legacy
  provider invitations remain available for existing groups.
- Steam package ancestry descriptors now bind each encrypted Workshop item to
  its group, active publisher certificate, unique version ID, parent descriptor,
  encryption epoch, payload checksum, and signature. Stable member-owned package
  indexes make unlisted items discoverable without exposing them to Workshop
  search. Discovery rejects spoofed, tampered, and revoked publishers and reports
  competing children as explicit forks instead of choosing the largest version.
- Administrator-controlled world unsharing, which removes the world from the
  group catalog while preserving the local save and Save Shift history.
- Editable local group names, with generated Cloudflare Worker identifiers
  replaced by a friendly default label.
- Multiple persisted groups with an active-group selector, creation and join
  flows that remain available while connected, and per-group invitations,
  computer management, departure, locks, and package catalogs.
- Explicit Local worlds and Shared worlds sections, group-name badges, and a
  Share action that associates a local world with the active group.
- Schema version 4 project-to-group associations and a backward-compatible
  migration that keeps existing coordinated worlds attached to the original
  group.
- New neon pixel-art branding assets for the Windows application icon and
  Steamworks banner artwork.
- A responsive portal-art header with the pixel Save Shift wordmark, plus a
  vaporwave interface palette, cyan and magenta controls, and retro monospace
  typography throughout the desktop app.
- A newly named multi-resolution Windows icon wired directly into PyInstaller,
  the application window, installer, Start Menu shortcut, desktop shortcut,
  uninstaller, and `.sspkg` file association to avoid stale blank icons.
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

- Improved the default-window layout with compact sidebar action rows and a
  responsive hero that grows on wide displays without stretching its artwork.
- Added a restrained vaporwave-orange accent to card outlines, section
  dividers, and scrollbars.

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
