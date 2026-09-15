# Save Shift

> Seamlessly hand off self-hosted co-op game worlds between friends.

Save Shift is a source-available Windows desktop application for sharing and managing locally hosted co-op game worlds. It packages a project's save files, tracks version history, and helps a group safely rotate who hosts the world.

[Download the latest release](https://github.com/XpWalnut/SaveShift/releases/latest)

> [!WARNING]
> Save Shift is alpha software. Back up important saves before testing it. The installer is currently unsigned, so Windows SmartScreen may show an "Unknown publisher" warning. Only install releases downloaded from this repository.

## Features

- Automatic game save-folder detection and project discovery
- Multi-library Steam installation detection for supported games
- Hosting a tracked project and launching its Steam game
- Exporting and importing portable `.sspkg` packages
- Structured package ancestry, source-device, notes, and game metadata
- Import previews with ancestry-aware conflict detection and backup confirmation
- Double-click `.sspkg` file associations on Windows
- Version history and restoration of previous saves
- World Journals for recording shared adventures, shown on project cards and carried in `.sspkg` handoffs
- Backup of an existing local save before an imported version is synchronized
- Automatic update checks through GitHub Releases, with an opt-out setting and manual checks
- Steam-native groups, friend invitations, signed online host presence, and
  package-ancestry conflict protection
- Project-card hosting status with active host and interrupted-session recovery
- A reusable profile name for history and host attribution
- Per-user Windows installer

## Supported games

- Abiotic Factor
- Schedule I
- Valheim
- V Rising

## Installation

1. Open the [latest GitHub release](https://github.com/XpWalnut/SaveShift/releases/latest).
2. Download the `SaveShiftSetup-<version>.exe` asset.
3. Compare its SHA-256 checksum with the value in the release notes.
4. Run the installer. If SmartScreen appears, confirm the installer came from this repository before selecting **More info** and **Run anyway**.

Save Shift installs for the current Windows user and does not require administrator privileges.

## Local data

Application data is stored under `%USERPROFILE%\.saveshift`:

- `data/saveshift.sqlite3` stores tracked games, projects, version history, and World Journal entries.
- `data/settings.json` stores application settings.
- `backups/` stores save backups.
- `packages/` stores generated packages.
- `logs/` stores application logs.
- `temp/` stores temporary working files.
- `locks/` stores operating-system lock files used to prevent concurrent local writes.

Uninstalling the application does not remove this data directory. Back it up before manually deleting it.

## Development

Save Shift targets Python 3.11 on Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest .\tests -q
python .\run_saveshift.py
```

The test configuration uses a temporary SQLite database, disables live update checks, and runs Qt with the offscreen platform. Tests must never access a user's real Save Shift database or game saves.

To create a release installer, install [Inno Setup 6](https://jrsoftware.org/isinfo.php) and run:

```powershell
.\tools\build_release.ps1
```

The build script runs the complete Python and Cloudflare regression suites, regenerates the bundled provider, and then runs PyInstaller and Inno Setup. Output is written to `dist/installer/`.

### Project coordination

Groups that rotate hosts can create or join a Steam-native group in Save Shift
and invite members through the Steam friend overlay. Group membership, package
indexes, and encryption-key envelopes are signed; save packages remain
encrypted in unlisted Steam Workshop items.

Choosing **Host** checks the latest package ancestry and creates signed online
hosting presence before launching the game. After the game closes, Save Shift
uploads the successor and clears that presence. If the app or computer exits
mid-session, a local checkpoint offers a safe handoff retry. Recovery refuses
to overwrite a group save that advanced elsewhere and keeps the local work as a
fork instead.

Steam presence is advisory rather than a durable lock. The descriptor ancestry
check is the final guard against two members publishing from the same starting
save. Existing Cloudflare groups remain supported during migration through the
provider-neutral [coordination API contract](coordination/openapi.yaml).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Changelog](docs/CHANGELOG.md)
- [Package format decision](docs/decisions/ADR-0001-package-format.md)
- [Fork behavior decision](docs/decisions/ADR-0002-fork-behavior.md)
- [Provider-neutral coordination decision](docs/decisions/ADR-0003-provider-neutral-coordination.md)
- [Cloudflare OAuth provisioning decision](docs/decisions/ADR-0004-cloudflare-oauth-provisioning.md)

## License

Save Shift is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use requires separate permission from the copyright holder. The Save Shift name, logo, application icon, and associated branding are covered by the [trademark notice](TRADEMARKS.md).

Versions previously published under the MIT License remain available under the license terms that applied to those versions.
