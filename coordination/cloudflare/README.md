# Save Shift Cloudflare coordination adapter

This directory implements the provider-neutral Save Shift coordination API with Cloudflare Workers and SQLite-backed Durable Objects. Nothing in the desktop imports this package or Cloudflare bindings.

## Release provisioning

Release builds bundle the minified Worker module into the desktop application. Save Shift's Cloudflare OAuth provisioner uploads that module, creates the `workers.dev` endpoint, supplies a one-time administrator bootstrap secret, and then revokes its temporary account access. Group members join with short-lived, single-use invitations and never interact with Cloudflare.

The public OAuth client is configured with `Memberships Read` and `Workers Scripts Write`. It uses Authorization Code with PKCE and does not embed a client secret.

Regenerate the bundled module after changing the Worker:

```powershell
pnpm run bundle
```

CI regenerates the module and fails if `app/resources/cloudflare/index.js` is stale.

## Manual development deployment

Manual deployment remains available for local development, recovery, and the Advanced custom-provider path.

### Prerequisites

- A Cloudflare account on the Workers Free plan.
- Node.js 20 or later.

### Local validation

```powershell
corepack enable
pnpm install --frozen-lockfile
pnpm test
pnpm run typecheck
```

### Configuration

Create the pairing code as a Worker secret. Share this code only with trusted group members:

```powershell
npx wrangler secret put PAIRING_CODE
```

The default lease is 900 seconds. `LEASE_SECONDS` may be changed in `wrangler.toml`, but values below 60 seconds are ignored.

### Deployment

```powershell
pnpm run deploy
```

After deployment, configure Save Shift with the generated `https://<worker>.workers.dev` endpoint and pair each computer using the shared pairing code.

## Portability contract

The adapter exposes `/api/v1` endpoints for administrator bootstrap, invitation joins, device administration and departure, legacy pairing, and project lock acquire, renew, release, and status operations. The final device departure calls `deleteAll()` so no group storage remains. The desktop depends only on that HTTP behavior. Cloudflare OAuth is a separate provisioning concern. A replacement provider can implement the same runtime contract without using Cloudflare, Durable Objects, or TypeScript.

Providers deployed by the earlier alpha can be upgraded without replacing their device identities. In Settings, enable **Advanced custom provider setup**, enter the original pairing code, and choose **Claim Administrator**. The provider permits this migration exactly once and only while no administrator exists.
