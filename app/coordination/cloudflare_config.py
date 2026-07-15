"""Public Cloudflare OAuth registration values embedded in Save Shift builds.

The client ID is not a secret. The registered client may remain private during
development, but must be promoted to public visibility before release.
Environment overrides remain available for isolated testing.
"""

CLOUDFLARE_OAUTH_CLIENT_ID = "31d534da75529944866a0f849e3e31b7"
CLOUDFLARE_OAUTH_SCOPES = (
    "memberships.read",
    "workers-scripts.write",
)
