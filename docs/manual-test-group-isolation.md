# Manual test: group package isolation

This test requires two newly created groups and at least two test computers or profiles.

1. Create Group A and join it from the second computer.
2. Hand off one recognizable project in Group A, then confirm it appears in **Shared Projects** on the second computer.
3. Remove the other computers from Group A and have the final computer leave it.
4. Create Group B and invite a different test computer or profile.
5. Before sharing anything, open **Shared Projects** in Group B.
6. Confirm the Group A project does not appear.
7. Hand off a different project in Group B.
8. Confirm Group B members see only the Group B project and cannot receive the Group A project.

Expected result: a newly created group always starts with an empty inbox. Its devices, locks, encryption keys, and shared-project catalog are isolated from every other group.
