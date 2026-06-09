import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

// Pin the workspace root to this folder so the stray lockfile in the user's home
// directory isn't inferred as the root (avoids the multiple-lockfiles warning).
const root = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  turbopack: { root },
  outputFileTracingRoot: root,
  // Emit a self-contained server (.next/standalone/server.js) so the Docker
  // image ships only the files it needs — see frontend/Dockerfile.
  output: "standalone",
};

export default nextConfig;
