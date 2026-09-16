import type { NextConfig } from "next";
import migrations from "./src/lib/route-migrations.json";

const nextConfig: NextConfig = {
  async redirects() {
    return migrations.filter(row => row.kind === "redirect").map(({ source, destination }) => ({ source, destination, permanent: true }));
  },
  // Baked in at build time, not read at runtime: this is what makes /api/version proof that
  // the SERVED ASSETS were built from this commit. A runtime read would only prove the process
  // restarted with a newer env, which is exactly the ambiguity CI-6 exists to remove.
  env: {
    NEXT_PUBLIC_COMMIT_SHA: process.env.RAILWAY_GIT_COMMIT_SHA ?? "unknown",
  },
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
