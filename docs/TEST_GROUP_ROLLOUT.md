# Test-group rollout and rollback

This procedure is for a large Save Shift alpha update. It assumes the group
owner retains a known-good copy of the authoritative world. Roll out to one
other person first; do not update the entire group simultaneously.

## Prepare the release

1. Keep the previous `SaveShiftSetup-0.1.0-alpha.3.exe` installer available.
2. Build the candidate with `.\tools\build_release.ps1`. Do not distribute it
   unless the regression suite and installer build both complete.
3. Record the Git commit used for the build in the Discord release message.
4. Ask everyone to stop hosting. The current host must close the game and wait
   until Save Shift reports that the handoff completed.
5. On one computer, receive and open the authoritative Valheim world. Confirm
   it is the expected latest state, then close the game without starting a new
   test session.
6. Keep an external copy or `.sspkg` export of that authoritative world. This
   is the recovery source if the test group must be recreated.
7. If using a Steam-native group, the administrator should export the
   password-protected administrator recovery kit and keep it outside the Save
   Shift data directory.

## Optional lightweight local checkpoint

This is recommended for the owner/admin development computer, but it is not
required for ordinary testers who are comfortable rejoining a newly created
group. With Save Shift closed, run this from a repository checkout:

```powershell
.\tools\create_rollout_checkpoint.ps1
```

The command stores a verified copy of only Save Shift's database and settings
under `%USERPROFILE%\.saveshift\backups\rollout`. It does not copy game saves
or upload anything. Save the printed checkpoint path.

## Canary rollout

1. Install alpha.4 on the group owner/admin computer and one other computer.
2. Launch both once and confirm Steam shows connected, the expected group name
   appears, and local/shared world sections are correct.
3. Create the Steam-native group and invite only the canary tester if this is a
   new Steam-only rollout. Start with a disposable world or copy, not Valheim.
4. Complete one full round trip: owner hosts and exits, tester receives/hosts
   and exits, then owner receives again.
5. During each leg verify the correct player attribution, exactly one version
   per handoff, hosting availability after game exit, journal behavior, and the
   ability to open the resulting world in the game.
6. Deliberately close Save Shift during one disposable session and exercise the
   interrupted-host recovery path.
7. If the canary is healthy, share the authoritative Valheim world and complete
   one owner-to-tester-to-owner round trip before inviting anyone else.

## Expand the rollout

Add one tester at a time. After each person joins:

1. Confirm their Steam identity and friendly group name.
2. Have them receive but not host the authoritative world.
3. Open the world only after the card reports the expected group version.
4. Perform a hosting round trip only after the previous tester's handoff is
   complete and the world reports **Available to host**.
5. Collect `%USERPROFILE%\.saveshift\logs\SaveShift.log` immediately if a
   transfer, lock, or recovery action fails.

## Stop conditions

Pause the rollout before inviting more testers if any of these occur:

- a handoff succeeds but another computer cannot discover it;
- two computers disagree about the authoritative head;
- a game opens the wrong local world after receiving;
- a hosting presence remains after a successful handoff;
- a package fails signature, ancestry, checksum, or extraction validation;
- the application cannot reopen its database after upgrading.

Do not work around an ancestry or integrity warning by repeatedly hosting. Keep
the relevant world files and logs unchanged until the failure is understood.

## Roll back to the develop build

1. Stop new sessions. If someone has unshared progress, close the game and let
   Save Shift hand it off. If handoff is broken, preserve that computer's save
   folder or export a package before continuing.
2. Close Save Shift and every supported game on that computer.

### Simple reset for tester computers

1. Open `%USERPROFILE%\.saveshift` in File Explorer and rename the `data`
   directory to something such as `data-alpha4-hold`. Do not delete it. This
   preserves the alpha.4 database, settings, Steam identity, and group cache
   while allowing develop to create clean compatible state.
2. Install `SaveShiftSetup-0.1.0-alpha.3.exe`, then launch it.
3. Re-detect installed games, create or join the older-style group, and
   import/copy the owner's authoritative Valheim world before anyone hosts.
4. Treat the alpha.4 Steam-native group as paused. Develop does not manage that
   group. Steam Workshop items remain intact and do not need to be deleted.

Keep `data-alpha4-hold` until the rollback test is finished. This method does
not change the actual Valheim save directory.

### Exact rollback on a computer with a checkpoint

Instead of renaming the data directory, restore the pre-update checkpoint
**before** installing or launching the older build:

```powershell
.\tools\restore_rollout_checkpoint.ps1 `
    -Checkpoint "C:\Users\NAME\.saveshift\backups\rollout\CHECKPOINT"
```

Type `ROLLBACK` when prompted. The tool validates the checkpoint and creates
another verified safety checkpoint of the current alpha.4 state before it
restores anything.

Then install `SaveShiftSetup-0.1.0-alpha.3.exe`. Recreate the group from the
owner's authoritative world if the restored settings do not describe a usable
develop-era group.

If a computer did not create a rollout checkpoint, close Save Shift and run
`.\tools\downgrade_database_to_develop.ps1` before installing develop. This
preserves saves and history but removes schema-4 project/group associations, so
the group and authoritative world must be configured again.

## Returning to alpha.4 after a rollback

Install alpha.4 again and let it migrate the develop database normally. Restore
the Steam administrator recovery kit only if the local Steam group identity or
manifest coordinates were lost. Do not restore an old database over newer world
files without first deciding which world copy is authoritative.
