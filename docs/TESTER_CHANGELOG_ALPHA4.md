# Save Shift 0.1.0-alpha.4 — Tester Notes

This is a large test update. Steam must be running and online while using
shared worlds.

## What changed

- New, quieter UI with clear **Local** and **Shared** world sections.
- Multiple named groups; each group has its own worlds and package history.
- New groups use Steam instead of Cloudflare.
- Invite friends from an in-app Steam friends list.
- Fixed a native Steam crash that could occur while inviting a friend as
  background hosting-status checks refreshed.
- Save Shift now listens for invitations addressed to your Steam account; the
  recipient no longer needs to press **Join Group** first.
- The friend picker is searchable, and either side can cancel an invitation
  wait immediately instead of waiting for its timeout.
- Partially completed joins can be retried safely if the administrator sees
  the computer but the recipient does not yet see the group.
- **Host** pulls the latest save, launches the game, and marks you as host.
- Closing the game automatically uploads the save and makes it available again.
- New group save versions are received automatically while Save Shift is idle.
- Steam coordination reconnects after the computer wakes from sleep.
- Hosting-status checks reuse a recently verified group manifest, and full
  package checks are consolidated to reduce noisy Workshop download bursts.
- Optional post-session journal entry and screenshot selection. Distinct
  mid-session screenshots now transfer encrypted with the exact save version.
- Admins can rename groups, unshare worlds, remove members, and back up group
  access. Removing a member rotates the key for future saves.
- Better crash recovery, version/fork detection, logging, and package security.
- Before an administrator hosts a world with more than 20 remote versions,
  shared-world history is compacted to keep the latest 20 recoverable remote
  versions. Steam only allows each account to delete its own Workshop
  uploads, so unused items from another member may disappear after that member
  next updates Save Shift.
- Updated branding and Windows icon.

## First-time setup

1. Install alpha.4 and keep Steam open.
2. Add or detect your installed games.
3. Admin: create a group. Tester: leave Save Shift open and signed into Steam.
4. Admin: choose **Invite a Friend**, find the tester, then have them accept
   the invitation in Steam. Save Shift completes the join automatically.
5. Use **Receive Shared World** for the initial world if it does not appear
   automatically. Later versions should arrive automatically while idle.

Normal flow after setup: **Host → play → close the game**. Keep Save Shift open;
it handles receiving, uploading, and releasing automatically.

## Please watch for

- Do not have two people press **Host** at the same time. If it happens, stop
  and decide who should continue.
- Do not repeatedly host through a fork, ancestry, signature, or integrity
  warning. Preserve the save and send the log.
- A Steam Workshop agreement may need to be accepted before the first upload.
- Windows Smart App Control may block this unsigned test build with error
  `0x11C7`. Report it; code signing is required for the permanent fix.
- After waking a PC, confirm the shared-world status changes from **Offline
  status unknown** back to **Available** without restarting Save Shift.
- Keep the game in the foreground periodically if you want automatic screenshot
  choices; Save Shift deliberately skips captures while you are Alt-Tabbed.
- If Save Shift or the PC closes mid-session, use **Recover Handoff**.
- Report the wrong world/version, a missing handoff, a world stuck as hosted,
  or a group showing another group's worlds.
- Logs are at `%USERPROFILE%\.saveshift\logs\SaveShift.log`.

## Rollback

Before returning to alpha.3/develop, close the game and Save Shift. Rename
`%USERPROFILE%\.saveshift\data` to `data-alpha4-hold`, install alpha.3, then
re-detect games and recreate/rejoin the old group from the known-good world.
Do not delete `data-alpha4-hold` until testing is complete.
