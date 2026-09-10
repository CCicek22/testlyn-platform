import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/firebase", () => ({
  getIdToken: vi.fn(),
  onAuthState: vi.fn(),
}));

import { shouldRetryQuery, defaultRetryDelay } from "./query-client";
import { UnauthenticatedError } from "./api-client";

describe("shouldRetryQuery", () => {
  it("never retries on UnauthenticatedError", () => {
    expect(shouldRetryQuery(0, new UnauthenticatedError())).toBe(false);
    expect(shouldRetryQuery(1, new UnauthenticatedError())).toBe(false);
  });

  it("retries once on network or CORS errors (failureCount = 0)", () => {
    expect(shouldRetryQuery(0, new TypeError("Failed to fetch"))).toBe(true);
    expect(shouldRetryQuery(0, new Error("CORS origin disallowed"))).toBe(true);
  });

  it("does not retry once failureCount reaches 1", () => {
    expect(shouldRetryQuery(1, new TypeError("Failed to fetch"))).toBe(false);
    expect(shouldRetryQuery(2, new Error("CORS origin disallowed"))).toBe(false);
  });
});

describe("defaultRetryDelay", () => {
  it("provides exponential backoff", () => {
    expect(defaultRetryDelay(0)).toBe(1000);
    expect(defaultRetryDelay(1)).toBe(2000);
    expect(defaultRetryDelay(2)).toBe(4000);
    expect(defaultRetryDelay(3)).toBe(8000);
  });

  it("caps retry delay at 10 seconds", () => {
    expect(defaultRetryDelay(4)).toBe(10_000);
    expect(defaultRetryDelay(5)).toBe(10_000);
    expect(defaultRetryDelay(10)).toBe(10_000);
  });
});
