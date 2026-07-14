# Save Shift Cloudflare coordination adapter

This directory implements the provider-neutral Save Shift coordination API with Cloudflare Workers and SQLite-backed Durable Objects. Nothing in the desktop imports this package or Cloudflare bindings.

## Prerequisites

- A Cloudflare account on the Workers Free plan.
- Node.js 20 or later.

## Local validation

```powershell
corepack enable
pnpm install --frozen-lockfile
pnpm test
pnpm run typecheck
```

## Configuration

Create the pairing code as a Worker secret. Share this code only with trusted group members:

```powershell
npx wrangler secret put PAIRING_CODE
```

The default lease is 900 seconds. `LEASE_SECONDS` may be changed in `wrangler.toml`, but values below 60 seconds are ignored.

## Deployment

```powershell
pnpm run deploy
```

After deployment, configure Save Shift with the generated `https://<worker>.workers.dev` endpoint and pair each computer using the shared pairing code.

## Portability contract

The adapter exposes `/api/v1` endpoints for device pairing and project lock acquire, renew, release, and status operations. The desktop depends only on that HTTP behavior. A replacement provider must implement the same contract; it does not need Durable Objects or TypeScript.
