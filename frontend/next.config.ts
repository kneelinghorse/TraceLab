import type { NextConfig } from "next";
import migrations from "./src/lib/route-migrations.json";

const nextConfig: NextConfig = {
  async redirects() {
    return migrations.filter(row => row.kind === "redirect").map(({ source, destination }) => ({ source, destination, permanent: true }));
  },
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
