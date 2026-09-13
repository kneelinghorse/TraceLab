import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      { source: "/missions/queue", destination: "/missions?view=queue", permanent: true },
      { source: "/invites", destination: "/settings#invites", permanent: true },
      { source: "/console", destination: "/admin/observability", permanent: true },
      { source: "/console/corrections", destination: "/admin/corrections", permanent: true },
      { source: "/console/missions", destination: "/missions", permanent: true },
      { source: "/console/missions/:id", destination: "/missions/:id", permanent: true },
    ];
  },
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
