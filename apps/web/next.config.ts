import type { NextConfig } from "next";

const firebaseProjectId =
  process.env["NEXT_PUBLIC_FIREBASE_PROJECT_ID"] ?? "example-project";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@testlyn/shared", "@testlyn/ui"],
  typescript: {
    // tsc --noEmit handles this; next build also checks
    ignoreBuildErrors: false,
  },
  // Proxy Firebase auth helper through the app's own origin so that
  // signInWithPopup works when COOP is active. Without this, the popup's
  // opener handle is severed because the default authDomain
  // (<project>.firebaseapp.com) is cross-origin to the app.
  // Pair with NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=<app-domain> at build time.
  async rewrites() {
    const firebaseBase = `https://${firebaseProjectId}.firebaseapp.com`;
    return [
      {
        source: "/__/auth/:path*",
        destination: `${firebaseBase}/__/auth/:path*`,
      },
      {
        source: "/__/firebase/:path*",
        destination: `${firebaseBase}/__/firebase/:path*`,
      },
    ];
  },
  // Server components can call the API directly; no rewrites needed for dev
  // when NEXT_PUBLIC_API_BASE_URL is set.
  experimental: {
    // React 19 stable — no flag needed
  },
};

export default nextConfig;
