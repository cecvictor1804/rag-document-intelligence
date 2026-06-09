import { resolve } from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    // Defaults so the auth modules (lib/auth/*) have credentials at import time.
    // AUTH_ENABLED is intentionally left unset (off) — the gating branches that
    // need it on are exercised by the backend tests.
    env: {
      AUTH_SECRET: "test-secret-please-change-test-secret-please",
      GOOGLE_CLIENT_ID: "test-client-id",
      GOOGLE_CLIENT_SECRET: "test-client-secret",
      GOOGLE_HOSTED_DOMAIN: "example.com",
      APP_URL: "http://localhost:3000",
    },
  },
  resolve: {
    alias: { "@": resolve(__dirname, ".") },
  },
});
