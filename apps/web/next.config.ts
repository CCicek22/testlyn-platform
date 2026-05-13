import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@testlyn/shared", "@testlyn/ui"],
  typescript: {
    // tsc --noEmit handles this; next build also checks
    ignoreBuildErrors: false,
  },
  // Server components can call the API directly; no rewrites needed for dev
  // when NEXT_PUBLIC_API_BASE_URL is set.
  experimental: {
    // React 19 stable — no flag needed
  },
};

export default nextConfig;
