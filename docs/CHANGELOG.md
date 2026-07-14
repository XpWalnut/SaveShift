# Changelog

All notable changes to Save Shift are documented here. The project is currently in alpha, so package and database compatibility may change before the first stable release.

## [Unreleased]

### Added

- Optional cross-device project leases for hosting, import, export, and restore workflows.
- Provider-neutral `/api/v1` coordination contract and Python HTTP adapter.
- Self-deployable Cloudflare Worker and SQLite-backed Durable Object adapter.
- Cross-process operating-system locks for destructive local save operations.
- Settings controls for provider URL, device pairing, and coordination opt-in.
- Windows DPAPI protection for stored device credentials.
- Python regression tests and Cloudflare contract tests for lock behavior.

### Changed

- Hosting retains and renews its project lease until export or application exit.
- Import and restore fail before touching save files when a remote lock cannot be verified.

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
