# Automatic hosting manual test

Use two computers connected to the same Save Shift group and a disposable test
world. Leave **Show manual Receive and Hand Off controls** disabled in Settings.

1. On computer A, host the world, change it in game, and exit the game while
   keeping Save Shift open.
2. Confirm Save Shift automatically uploads a new version and releases the lock.
3. On computer B, choose **Host** without first choosing Receive.
4. Confirm Save Shift downloads computer A's latest version before launching the
   game.
5. Verify computer A's change is present, make a different change, then exit.
6. Confirm computer B automatically uploads the next version and releases the
   lock.
7. On computer A, choose **Host** again and confirm computer B's change is
   present.
8. While the game is running, try to close Save Shift. Confirm it refuses and
   explains that it must remain open for automatic handoff.
9. With the game already open outside Save Shift, choose **Host**. Confirm Save
   Shift refuses to replace save files and asks you to close the game first.
10. Enable **Show manual Receive and Hand Off controls** in Settings and confirm
    those two buttons appear for troubleshooting.
