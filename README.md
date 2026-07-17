# Save Shift

> Seamlessly hand off self-hosted co-op game worlds between friends.

Save Shift is a source-available Windows desktop application for sharing and managing locally hosted co-op game worlds. It packages a project's save files, tracks version history, and helps a group safely rotate who hosts the world.

[Download the latest release](https://github.com/XpWalnut/SaveShift/releases/latest)

> [!WARNING]
> Save Shift is alpha software. Back up important saves before testing it. The installer is currently unsigned, so Windows SmartScreen may show an "Unknown publisher" warning. Only install releases downloaded from this repository.

## Features

- Automatic game save-folder detection and project discovery
- Hosting a tracked project and launching its Steam game
- Exporting and importing portable `.sspkg` packages
- Double-click `.sspkg` file associations on Windows
- Version history and restoration of previous saves
- World Journals for recording shared adventures, shown on project cards and carried in `.sspkg` handoffs
- Backup of an existing local save before an imported version is synchronized
- Automatic update checks through GitHub Releases, with an opt-out setting and manual checks
- Optional cross-device project locking through a user-owned coordination provider
- Project-card lock status with current owner and lease expiration
- A reusable profile name for history and lock attribution
- Per-user Windows installer

## Supported games

- Abiotic Factor
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

### Optional project coordination

Groups that rotate hosts can create or join a group from **Settings → Project Coordination**. The organizer authorizes Cloudflare in their browser; Save Shift deploys the user-owned provider and generates single-use invitations for friends. Other members only paste the invitation into Save Shift. Save Shift acquires a renewable lease while a project is hosted and short-lived leases around import and restore. Project cards show the current owner and lease expiration. If the provider cannot confirm ownership, the destructive operation is stopped before save files are changed.

Any paired computer can leave from Settings. Administrators must revoke other active computers before leaving. When the final computer leaves, Save Shift clears the group's Durable Object storage and, for automatically provisioned groups, asks the Cloudflare owner to authorize deletion of the Worker.

The registered Cloudflare OAuth client uses `Memberships Read` and `Workers Scripts Write`. It may remain private for development, but its publisher domain must be verified and the client promoted to public visibility before release builds are distributed.

Cloudflare is not embedded in the desktop application. The desktop uses the provider-neutral [coordination API contract](coordination/openapi.yaml), so another HTTPS service can replace the included adapter without rewriting application workflows. Deployment instructions are in the [Cloudflare adapter README](coordination/cloudflare/README.md).

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
