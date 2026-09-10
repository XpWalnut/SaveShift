import { cloudflareTest } from "@cloudflare/vitest-pool-workers";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [
    cloudflareTest({
      wrangler: { configPath: "./wrangler.toml" },
      miniflare: {
        bindings: {
          GROUP_ID: "test-group",
          PAIRING_CODE: "test-pairing-code",
          ADMIN_BOOTSTRAP_TOKEN: "test-bootstrap-token",
          LEASE_SECONDS: "900"
        }
      }
    })
  ]
});
