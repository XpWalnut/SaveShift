# Manual test: group package isolation

This test requires two newly created groups and at least two test computers or profiles.

1. Create Group A and join it from the second computer.
2. Share and hand off one recognizable project in Group A, then confirm it appears in **Receive Shared World** on the second computer.
3. Without leaving Group A, create Group B and invite a different test computer or profile.
4. Switch between Group A and Group B from the group selector. Confirm the selected group survives an application restart.
5. Confirm the first project appears under **Shared worlds** with a Group A badge. Confirm an unshared world appears under **Local worlds**.
6. With Group B active, open **Receive Shared World** and confirm the Group A project does not appear.
7. Share and hand off a different project in Group B.
8. Switch back to Group A and confirm Group A members see only the Group A project. Switch to Group B and confirm Group B members see only the Group B project.
9. Leave Group B. Confirm its local project becomes Local while Group A remains configured and selectable.

Expected result: each group retains its own credentials, devices, locks, encryption keys, project associations, and package catalog. Switching one group never exposes another group's packages, and leaving one group does not disconnect the others.
