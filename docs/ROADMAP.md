# Roadmap

Save Shift is currently stabilizing its alpha feature set. This roadmap describes direction, not a fixed release schedule.

## Alpha stabilization

- Publish the registered Save Shift Steamworks configuration and validate encrypted UGC transfers between two licensed accounts.
- Validate the connected project-card Receive and Hand Off controls across two licensed Steam accounts.
- Replace manual package sharing as the normal coordinated handoff path while retaining export/import as an offline fallback.
- Exercise installer-based updates across consecutive published releases.
- Expand manual testing across supported games and unusual save layouts.
- Improve error reporting and recovery for interrupted package operations.
- Keep the regression suite and Windows release build green.
- Resolve issues found by early testers without expanding the core feature set.
- Exercise coordinated handoffs with multiple physical computers and provider outages.
- Verify the Save Shift publisher domain and promote the registered Cloudflare OAuth client to public visibility.
- Exercise Create Group and invitation onboarding against a clean Cloudflare account.

## Beta readiness

- Exercise the complete host, publish, download, conflict-preview, import, and next-host workflow across two physical computers.
- Validate versioned database migrations against databases produced by every published alpha release.
- Define and test `.sspkg` compatibility guarantees.
- Improve onboarding, empty states, and troubleshooting guidance.
- Review backup retention and storage-management controls.
- Add more supported games only after their discovery and synchronization behavior can be covered deterministically.

## Later possibilities

- Package signing and a signed Windows installer.
- Alternative coordination adapters implementing the stable `/api/v1` contract.
- Additional backup strategies and retention policies.
- Additional operating-system support.

Completed work is recorded in the [changelog](CHANGELOG.md). Feature requests and defects can be submitted through [GitHub Issues](https://github.com/XpWalnut/SaveShift/issues).
