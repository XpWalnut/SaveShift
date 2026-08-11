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
