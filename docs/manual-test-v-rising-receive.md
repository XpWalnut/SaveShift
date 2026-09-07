# V Rising cross-PC receive manual test

Use a disposable V Rising world. Both testers must run the new Steam build.

## First receive

1. On Jake's PC, open V Rising once and confirm the disposable world loads.
2. Close V Rising completely, then host and hand off that world in Save Shift.
3. On the receiving PC, configure V Rising in Save Shift but do not create a
   world with the same name.
4. Open Shared Projects, select the handed-off world, and approve the import.
5. Confirm Save Shift reports a successful receive instead of "Import Not
   Allowed."
6. Launch V Rising and confirm the received world appears and loads.

## Subsequent receive

1. On the receiving PC, make a harmless, recognizable change in the test world,
   then hand it back.
2. On Jake's PC, receive the newer version and approve the backup/replacement
   prompt if shown.
3. Launch V Rising and confirm the recognizable change is present.

## Diagnostics

If either receive fails, collect `%USERPROFILE%\.saveshift\logs\SaveShift.log`
from both PCs and capture the complete error dialog. Do not delete either local
world until the round trip is confirmed.

Packages exported by older Save Shift builds without `metadata.game_metadata`
and `world_uuid` cannot be imported safely. Re-host and hand off the world from
the current build to create a compatible package.
