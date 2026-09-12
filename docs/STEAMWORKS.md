# Steamworks development

Save Shift is registered as Steam AppID `5096900`. Steam UGC is the first remote
blob transport for encrypted group packages. Cloudflare remains the source of
truth for membership, leases, package descriptors, and encryption-key epochs.

## Dashboard configuration

Before live UGC testing:

1. Configure a per-user Steam Cloud byte and file quota.
2. Enable **ISteamUGC for file transfer** under Workshop configuration.
3. Keep Workshop visibility at **Developers & Testers** while developing.
4. Publish the configuration changes through **Prepare for Publishing**.
5. Ensure every test account owns a testing license for AppID `5096900`.

Every Steam account that publishes an item may need to accept the Steam Workshop
legal agreement once. Save Shift surfaces the returned item page when Steam says
that acceptance is required.

## Local SDK

Do not commit the Steamworks SDK, its archive, or `steam_appid.txt`. Extract the
official SDK outside the repository and set:

```powershell
$env:STEAMWORKS_SDK_PATH = "C:\Users\you\sdk"
```

For this development machine the SDK is currently at `C:\Users\jjbou\sdk`.
`tools/build_release.ps1` also checks `$HOME\sdk` when the environment variable
is absent. The expected redistributable is:

```text
redistributable_bin\win64\steam_api64.dll
```

## Uploading a private Steam build

The repository provides one upload command for AppID `5096900` and Windows
depot `5096901`:

```powershell
.\tools\upload_steam_build.ps1 -SteamUsername "YOUR_STEAM_USERNAME"
```

The script runs the normal Save Shift release build, verifies the unpacked
`dist\SaveShift` application, creates temporary SteamPipe configuration under
the ignored `build\steampipe` directory, and starts the SDK's SteamCMD uploader.
SteamCMD may prompt for the account password and Steam Guard code; neither is
written to the generated configuration.

After the first upload, refresh **Steamworks > SteamPipe > Builds**, create a
password-protected branch named `cross-machine-test`, and set the uploaded build
live on that branch. Upload the unpacked application directory through this
workflow; the Inno Setup installer is only for non-Steam distribution.

For a configuration-only check that does not contact Steam, reuse an existing
release build and add both switches:

```powershell
.\tools\upload_steam_build.ps1 `
    -SteamUsername "YOUR_STEAM_USERNAME" `
    -SkipBuild `
    -DryRun
```

For a source-tree launch, either start Save Shift through Steam or create a local
ignored `steam_appid.txt` containing only:

```text
5096900
```

That development file must not ship. PyInstaller receives `steam_api64.dll`
through `SAVESHIFT_STEAM_API_PATH`, which the release script derives from the SDK
location, and places it in the packaged runtime.

## Architecture

`SteamworksUgcClient` dynamically loads the official flat C API and uses manual
callback dispatch. It provides only the operations Save Shift needs: create and
submit an item, download and locate installed content, and delete an item.

`SteamUgcBlobTransport` presents those operations as an opaque blob provider. It
always publishes unlisted items, uploads a folder containing `package.ssenc`, and
copies downloads out of Steam's cache. The outer `EncryptedPackageTransport`
encrypts and authenticates the original `.sspkg`; Steam never receives plaintext
save data.

All Steam tests mock the SDK boundary. Live testing requires the Steam client,
the official DLL, published UGC configuration, and licensed test accounts.

## Validated live behavior

On August 11, 2026, SDK v1.65 successfully initialized for AppID `5096900` and
completed a controlled same-account test: create an unlisted item, upload an
opaque payload, download it through Steam, verify every byte, and delete it. The
temporary item was removed after verification. The remaining release gate is a
full encrypted package handoff between two separately licensed Steam accounts.

Steam can emit a transient failed `DownloadItemResult_t` while its client keeps
retrying the Workshop manifest in the background. Save Shift therefore monitors
the item's state until it is installed and no longer pending or updating, rather
than treating an early connection or timeout result as immediate transfer
failure.

## First transfer to another computer

After one group member uses **Hand Off**, a newly joined computer does not need
an emailed or Discord-shared `.sspkg`. Choose **Shared Projects** in Save Shift,
select the project in the Group Inbox, and choose **Receive Project**. Save Shift
downloads the encrypted Steam item, previews the import, discovers the correct
game save target, and creates the local project after confirmation.

Existing development groups must redeploy the coordination Worker once after
pulling this change so their provider exposes the group inbox endpoint:

```powershell
cd coordination\cloudflare
pnpm exec wrangler deploy --name "YOUR_EXISTING_WORKER_SCRIPT_NAME"
```

Use the existing script name from the group's `workers.dev` URL (for example,
`saveshift-coordination-4fb73f`). Keeping the same name upgrades that Worker and
preserves its Durable Object group data; a different name would create a
separate provider.

New groups created by a release build receive the updated bundled Worker
automatically.

## Branding assets

Steam artwork is managed in the Steamworks dashboard; it is not included in a
SteamPipe depot upload. The repository keeps the supplied source artwork in:

- `assets/icons/SaveShift.png` — square 1254 x 1254 source artwork.
- `assets/steam/SaveShift-Banner.png` — wide 1834 x 857 Steam artwork.

Steam-ready exports derived from those originals are:

- `assets/steam/SaveShift-ShortcutIcon-512.png` — **Shortcut Icon**.
- `assets/steam/SaveShift-AppIcon-184.jpg` — **App Icon**.
- `assets/steam/SaveShift-Header-920x430.png` — **Store Header Capsule** and
  **Library Header**.
- `assets/steam/SaveShift-LibraryHero-3840x1240.png` — **Library Hero**.
- `assets/steam/SaveShift-LibraryLogo-1280x720.png` — transparent **Library
  Logo**.

Upload the Shortcut Icon and App Icon under **App Admin > Installation > Client
Images**. Upload the 920 x 430 header under **Edit Store Page > Graphical
Assets** for the Store Header Capsule and Library Header fields. Upload the
3840 x 1240 background and transparent 1280 x 720 title artwork as the Library
Hero and Library Logo respectively. Keep the larger repository files as
uncropped sources for any additional capsule variants.

`assets/icons/SaveShift.ico` is a generated multi-resolution Windows icon. It
contains 16, 24, 32, 48, 64, 128, and 256 pixel variants and is already shared
by the application window, PyInstaller executable, Inno Setup installer, Start
menu shortcut, and optional desktop shortcut.
