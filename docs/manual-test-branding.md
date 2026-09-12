# Branding manual test

1. Run `./tools/build_release.ps1` and confirm the release build completes.
2. Install the newly generated installer over the current Save Shift install.
3. Confirm the new neon icon appears on `SaveShift.exe`, the application window,
   the Start menu shortcut, and a newly created desktop shortcut.
4. If Windows still shows the old shortcut icon, delete and recreate the
   shortcut or restart Windows Explorer to refresh the icon cache.
5. Open the three `assets/steam/SaveShift-*` Steam-ready exports and confirm
   their artwork is sharp and uncropped.
6. Under **App Admin > Installation > Client Images**, confirm Steamworks accepts
   the 512 x 512 Shortcut Icon and 184 x 184 App Icon.
7. Under **Edit Store Page > Graphical Assets**, confirm Steamworks accepts the
   920 x 430 image as the Store Header Capsule and Library Header.
8. Upload the 3840 x 1240 Library Hero and transparent 1280 x 720 Library Logo,
   then use Steam's preview to choose the preferred logo position.
