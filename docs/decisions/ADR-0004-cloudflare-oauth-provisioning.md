# ADR-0004: Cloudflare OAuth Provider Provisioning

## Status

Accepted

## Context

Provider-neutral coordination protects Save Shift projects across computers, but manually installing Node.js, pnpm, Wrangler, and configuring Worker secrets is not an acceptable onboarding experience for ordinary players. The group organizer should not need to understand or maintain Cloudflare infrastructure.

Save Shift must not embed an account API token or a confidential OAuth client secret in the desktop executable. It also must not retain broad access to a user's Cloudflare account after setup.

## Decision

Save Shift will register a public Cloudflare OAuth client and use Authorization Code with PKCE through the user's system browser. The client requests `Memberships Read` to discover the authorized account and `Workers Scripts Write` to deploy its provider.

After authorization, a Cloudflare-specific provisioning adapter will:

- Find the Cloudflare account selected during consent.
- Create a random `workers.dev` account subdomain when necessary.
- Upload the bundled and tested coordination Worker through the Workers API.
- Provision its SQLite Durable Object migration and bindings.
- Generate a random, one-time administrator bootstrap secret.
- Enable and verify the Worker endpoint.
- Bootstrap the organizer's computer as the group administrator.
- Revoke the temporary OAuth access token after provisioning.

The provisioning adapter is separate from `CoordinationProvider`. Runtime locking and group membership continue to use the provider-neutral `/api/v1` contract. Alternative providers do not need to implement Cloudflare OAuth.

Group members join with short-lived, single-use Save Shift invitations. Provider URLs and invitation tokens are encoded into the invitation text and are not presented as infrastructure settings. Raw provider configuration remains available under Advanced for custom providers and recovery.

Publishing the OAuth client requires a verified Save Shift publisher domain. The public client ID is not secret and is embedded in release builds only after registration. A local environment override supports development before registration.

## Consequences

- The normal organizer flow becomes Create Group, authorize Cloudflare, and wait for Save Shift to finish.
- Group members do not need Cloudflare, GitHub, Node.js, pnpm, or Wrangler.
- Save Shift does not retain a Cloudflare refresh token or long-lived account credential.
- Cloudflare's `Workers Scripts Write` permission is account-scoped, so the consent UI must clearly explain the temporary access.
- Provider upgrades require another explicit Cloudflare authorization unless Cloudflare offers a narrower durable update mechanism later.
- The bundled Worker must be regenerated and verified in CI whenever its TypeScript source changes.
- OAuth client registration and publisher-domain verification remain release prerequisites outside the repository.
