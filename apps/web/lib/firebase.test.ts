import { beforeAll, describe, expect, it, vi } from "vitest";

let resolveAuthDomain: (
  configured?: string | undefined,
  loc?: { protocol: string; hostname: string } | undefined,
) => string | undefined;

const CONFIGURED = "dev.testlyn.example.com";

beforeAll(async () => {
  // firebase.ts calls initializeApp/getAuth at module load, which throws
  // auth/invalid-api-key without real credentials. The dev-bypass flag skips
  // that block, leaving the pure resolver importable on its own.
  vi.stubEnv("NEXT_PUBLIC_DEV_AUTH_BYPASS", "true");
  ({ resolveAuthDomain } = await import("./firebase"));
});

describe("resolveAuthDomain", () => {
  it("uses the serving host on https, so one build works on both hostnames", () => {
    // The apex and the dev host both map to testlyn-web. A static authDomain is
    // cross-origin — and so COOP-broken — on whichever one it is not.
    expect(
      resolveAuthDomain(CONFIGURED, {
        protocol: "https:",
        hostname: "testlyn.example.com",
      }),
    ).toBe("testlyn.example.com");

    expect(
      resolveAuthDomain(CONFIGURED, {
        protocol: "https:",
        hostname: "dev.testlyn.example.com",
      }),
    ).toBe("dev.testlyn.example.com");
  });

  it("falls back to the configured value during SSR / prerender", () => {
    expect(resolveAuthDomain(CONFIGURED, undefined)).toBe(CONFIGURED);
  });

  it("falls back on non-https origins so local dev keeps its port", () => {
    // hostname drops the port: http://localhost:3000 would otherwise yield an
    // authDomain of "localhost" and a popup at https://localhost/__/auth/handler.
    expect(
      resolveAuthDomain(CONFIGURED, {
        protocol: "http:",
        hostname: "localhost",
      }),
    ).toBe(CONFIGURED);
  });

  it("passes an undefined configured value through untouched", () => {
    expect(resolveAuthDomain(undefined, undefined)).toBeUndefined();
  });
});
