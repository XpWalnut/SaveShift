# Valheim chunked-world manual test

Use a disposable world and close Valheim before hosting, receiving, or inspecting
its save files.

1. Create a new local Valheim world and enter it once so Valheim writes its save.
2. Exit Valheim completely, then restart Save Shift.
3. Select Valheim. Confirm the new world appears once and that an automatic
   backup with a similar name does not appear as another project.
4. Host the new world and hand it off through a disposable Save Shift group.
5. On the second PC, install the build containing this change, configure Valheim,
   open Shared Projects, and receive the world.
6. Launch Valheim and confirm the world appears and loads.
7. Make a recognizable harmless change, exit Valheim, and hand the world back.
8. Receive it on the first PC, then confirm the change in Valheim.

If a step fails, preserve both copies of the world, capture the full error dialog,
and collect `%USERPROFILE%\.saveshift\logs\SaveShift.log` from both PCs.

## Legacy flat-world isolation

1. With at least two old-format `.db` worlds in `worlds_local`, host only one.
2. Open its generated `.sspkg` as a ZIP and inspect `manifest.json`. Confirm the
   `files` list contains only the selected world's `.db` and optional `.fwl`.
3. Receive that package while another flat world exists on the destination PC.
   Confirm the unrelated world's files remain unchanged.
4. An older package containing several worlds should be rejected with directions
   to re-host it using the current Save Shift version.
