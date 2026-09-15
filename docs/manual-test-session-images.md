# Session image manual test

Use this test on a non-sensitive test world. Save Shift captures only the
supported game's visible window; it must never fall back to the desktop or an
unrelated application.

1. In Settings, enable **Capture a few game-window images during hosted sessions**.
2. Host a shared test world and play with it in the foreground for at least
   6 minutes. Save Shift begins after two minutes, samples every three minutes,
   rejects near-duplicates, and keeps the four most recent distinct frames.
3. Exit the game and do not interact with the computer while Save Shift creates
   and uploads the handoff.
4. Confirm the hosting presence is released before the session-image chooser
   appears. Another group member should now see the world as available.
5. Confirm every offered candidate contains only the game window. Select one
   and verify it appears, cropped without distortion, on the world card. On a
   second group computer, receive that exact save and confirm the same image
   appears there.
6. Repeat and choose **Choose My Own…**. Select a normal PNG or JPEG and verify
   it appears on the card.
7. Repeat and choose **No Image**. Confirm the previous card image is removed.
8. Disable the setting, host again, and confirm no captures or chooser appear.
9. Alt-Tab away across one or more sampling times and confirm Save Shift skips
   those frames instead of capturing the other application.
10. Force the game into an exclusive-fullscreen mode that cannot be captured.
   Confirm Save Shift offers no blank desktop capture and still allows
   **Choose My Own…** or **No Image** after the completed handoff.
