# Manual test: host and handoff versioning

Use a group project that is already synchronized and shows a current version.

1. Record the version number shown on the project card (for example, version 5).
2. Click **Host**.
3. Confirm Save Shift acquires the project lock and launches the game.
4. Return to Save Shift and confirm the project still shows the same version number.
5. Make a recognizable change in the game, save, and close the game.
6. Click **Hand Off** and complete the handoff.
7. Confirm the project now shows exactly the next version (version 6 in this example), not version 7.
8. On another group computer, open **Shared Projects**, receive the project, and confirm it receives that same version and the in-game change.
9. Open **History** and confirm there is one new row for the session, attributed to the person who handed it off.

Expected result: **Host** only claims the lock and launches the game. **Hand Off** creates and shares exactly one new project version.
