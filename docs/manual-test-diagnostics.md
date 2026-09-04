# Diagnostic logging manual test

Use a disposable world and the newly built application on both PCs. Older Steam
builds will not contain these changes. Logs stay local; nothing is uploaded.

1. Launch Save Shift, open Shared Projects, and close the result dialog.
2. Press Win+R and open `%USERPROFILE%\.saveshift\logs`.
3. Open `SaveShift.log`. Expect `operation=catalog.list` started/completed entries
   with matching IDs, elapsed time, and a catalog count (zero is valid).
4. Hand off a test world on PC A and receive it on PC B. Expect publish/receive,
   catalog, upload, and download/decrypt/validation operation entries on the
   relevant machine. Successful operations end with `completed`.
5. If a Steam download stalls, inspect the log while it is waiting. Expect
   `steam.download waiting` about every 15 seconds, including item ID and state.
   Callback results, retries and timeout are logged when they occur.
   A stalled Steam download should report an error after approximately 60 seconds
   in the Steam download phase (catalog/setup time is additional), not five minutes.
   This is a total download deadline, including retries, not an inactivity timer.
   Uploads retain their existing five-minute allowance.
6. Test group creation/join with a disposable group. Expect `group.create` or
   `group.join` started/completed entries. Cancel authorization to exercise an
   error; expect `failed`, an exception type, and stack function/line locations.
7. For a bug report, attach logs from both PCs and note which PC performed each
   action, approximate time, app build, and the exact UI error screenshot.

The log rotates at approximately 2 MB with three backups (`SaveShift.log.1` to
`.3`). New diagnostics omit arguments, exception messages, OAuth URLs, tokens,
invite codes, encryption keys, and save contents. Existing application log
messages may contain local paths, display names, and project identifiers;
review files before sharing and send them privately.
