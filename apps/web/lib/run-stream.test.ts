import { describe, expect, it } from "vitest";
import { mapFrameMetrics } from "./run-stream";
import type { RunStreamFrame } from "@testlyn/shared";

function frame(overrides: Partial<RunStreamFrame> = {}): RunStreamFrame {
  return {
    run_id: "run-1",
    state: "running",
    metrics: [],
    ...overrides,
  };
}

describe("mapFrameMetrics", () => {
  it("maps backend wire fields (p95_duration_ms/vus) to LiveSample (p95/vu_count)", () => {
    const seen = new Set<string>();
    const samples = mapFrameMetrics(
      frame({
        metrics: [
          { ts: "2026-06-10T00:00:00Z", p95_duration_ms: 123, error_rate: 0.05, vus: 7 },
        ],
      }),
      seen
    );
    expect(samples).toHaveLength(1);
    expect(samples[0]).toMatchObject({
      ts: "2026-06-10T00:00:00Z",
      run_id: "run-1",
      p95: 123,
      error_rate: 0.05,
      vu_count: 7,
    });
    // p50 unavailable on this wire — NaN sentinel guarded by the stat card.
    expect(Number.isNaN(samples[0]!.p50)).toBe(true);
  });

  it("dedupes by ts across overlapping frames", () => {
    const seen = new Set<string>();
    const m1 = { ts: "2026-06-10T00:00:01Z", p95_duration_ms: 100, error_rate: 0, vus: 1 };
    const m2 = { ts: "2026-06-10T00:00:02Z", p95_duration_ms: 110, error_rate: 0, vus: 1 };
    const first = mapFrameMetrics(frame({ metrics: [m1, m2] }), seen);
    // Backend re-sends the last 60s window each tick — overlap must be dropped.
    const second = mapFrameMetrics(
      frame({
        metrics: [m2, { ts: "2026-06-10T00:00:03Z", p95_duration_ms: 120, error_rate: 0, vus: 2 }],
      }),
      seen
    );
    expect(first).toHaveLength(2);
    expect(second).toHaveLength(1);
    expect(second[0]!.ts).toBe("2026-06-10T00:00:03Z");
  });

  it("skips null ts and null p95 maps to 0", () => {
    const seen = new Set<string>();
    const samples = mapFrameMetrics(
      frame({
        metrics: [
          { ts: null, p95_duration_ms: 50, error_rate: 0, vus: 1 },
          { ts: "2026-06-10T00:00:05Z", p95_duration_ms: null, error_rate: 0.1, vus: 3 },
        ],
      }),
      seen
    );
    expect(samples).toHaveLength(1);
    expect(samples[0]!.p95).toBe(0);
  });
});
