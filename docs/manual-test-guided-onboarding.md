# Guided onboarding manual test

Use a Windows account that has Steam and at least one supported game. Ideally,
include a newly installed game that has never created a save. For the cleanest
test, remove that account's existing Save Shift
settings and database first, or use a new Windows profile.

1. Launch Save Shift.
2. Confirm supported Steam games appear automatically, including a game that
   does not have a save folder yet. It should show zero projects rather than
   being omitted.
   If none appear, use **Detect Steam Games** and confirm the result is explained.
3. Confirm **Create Group** and **Join Group** are on the main screen and
   **Receive Shared World** is not shown yet.
4. Hover over **Join Group**, **Detect Steam Games**, and **How It Works**.
   Confirm each tooltip describes the action in plain language.
5. Open **How It Works**. Confirm it explains the complete cycle:
   Receive → Host → play → exit the game → Hand Off.
6. On an existing group administrator's computer, choose **Invite a Friend**
   and copy the invitation.
7. On the new computer, choose **Join Group** on the main screen. Enter a
   display name if prompted and paste the invitation.
8. After the join succeeds, confirm Save Shift automatically detects supported
   Steam games and immediately checks for shared worlds. No separate visit to
   Settings or click on Detect Steam Games should be required.
9. Select the shared world and complete its import.
10. Confirm the imported project's buttons are **Host**, **Receive**, **Hand
   Off**, **History**, and **Journal**. Hover over each and verify its purpose is
   explained.
11. Choose **Host**. Confirm the game launches and the button changes to
    **Hosting**.
12. Exit the game, choose **Hand Off**, and confirm the new version uploads and
    the group lock becomes available.
