# Group timeline reconciliation manual test

Use two test computers that belong to the same Save Shift group.

1. On computer A, create or select a test project and record local versions until
   its card shows a higher number than the version currently shared by the group.
2. On computer B, hand off the group's authoritative project version.
3. On computer A, click **Receive**. Confirm the review dialog says **Group
   handoff differs from local history** instead of blocking the older package.
4. Check the acknowledgement and click **Sync to Group Version**.
5. Confirm Save Shift creates a backup and the project card now shows the received
   group version. Open the game and verify the received world state is present.
6. Open **History**. Confirm the received version is marked **Current** and the
   previous higher-numbered local versions are still listed.
7. Hand off from computer A. Confirm the new package version is one greater than
   the received group version and computer B can receive it normally.

If any step fails, do not overwrite the backup. Collect
`%USERPROFILE%\.saveshift\logs\SaveShift.log` from both computers.
