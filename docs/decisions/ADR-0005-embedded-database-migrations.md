# ADR-0005: Embedded Database Migrations

## Status

Accepted

## Date

2026-07-16

---

## Context

Save Shift stores installed games, discovered projects, and project history in a user-owned SQLite database. Alpha releases previously created missing tables with SQLAlchemy and contained one ad-hoc column check. Session Journals and later beta features require repeatable schema changes that preserve databases created by installed releases.

The Windows application is distributed as a PyInstaller bundle. Database upgrades must run without a developer environment, must not depend on an external migration command, and must stop safely when the database cannot be identified.

## Decision

Save Shift will use a small embedded migration registry under `app/database/migrations`.

- SQLite `PRAGMA user_version` records the current schema version.
- Each migration has a monotonically increasing target version and an ordered Python function.
- Fresh databases are created directly from current SQLAlchemy metadata and stamped with the current version.
- Databases from pre-migration alpha releases are adopted only when their required tables and columns match a known schema.
- Unknown, incomplete, internally inconsistent, and newer schemas are rejected before migration.
- A consistent SQLite backup is created before the first pending migration.
- All pending migrations are attempted in order during startup before repositories are used.
- If a migration fails, Save Shift restores the pre-migration backup automatically and retains the backup for diagnosis.

The current migration history defines schema version 1 as the early alpha schema without `project_versions.restored_from_version_id`, schema version 2 as the published alpha schema containing that column, and schema version 3 as the schema adding `session_journal_entries`.

## Consequences

### Advantages

- Installed builds upgrade their own data without a separate CLI.
- Migration code remains small, explicit, and covered by the normal pytest suite.
- Existing alpha databases can be adopted without falsely claiming arbitrary SQLite files are compatible.
- A failed migration does not leave the user on a partially upgraded schema.
- Databases opened by a newer Save Shift release are not downgraded accidentally.

### Disadvantages

- Each schema change requires a forward migration and an updated current-version constant.
- Complex table rebuilds must account for SQLite-specific behavior explicitly.
- The embedded runner does not provide Alembic's automatic revision generation or downgrade graph.

## Follow-up

- Test upgrades from database fixtures produced by each published alpha release.
- Add retention controls for old database backups.
- Reevaluate a larger migration framework if schema evolution becomes complex enough to justify its packaging and operational cost.
