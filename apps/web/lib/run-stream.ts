/**
 * Mapping helpers for the run live-stream SSE wire format.
 *
 * The API (`GET /v1/runs/:id/stream`) emits plain `data:` frames shaped as
 * `RunStreamFrame` — `{ run_id, state, metrics: [{ ts, p95_duration_ms,
 * error_rate, vus }, ...] }` — where `metrics` is the last-60s window
 * re-queried every tick, so consecutive frames overlap heavily.
 */

import type { LiveSample, RunStreamFrame } from "@testlyn/shared";

/**
 * Map a stream frame's metrics into `LiveSample`s for the chart / stat cards,
 * deduping by `ts` via the caller-owned `seen` set (frames overlap).
 * Entries with a null `ts` are skipped. `p50` is unavailable on this wire and
 * is set to the NaN sentinel the p50 stat card guards on.
 */
export function mapFrameMetrics(
  frame: RunStreamFrame,
  seen: Set<string>
): LiveSample[] {
  const out: LiveSample[] = [];
  for (const m of frame.metrics ?? []) {
    if (!m.ts || seen.has(m.ts)) continue;
    seen.add(m.ts);
    out.push({
      ts: m.ts,
      run_id: frame.run_id,
      metric_name: "http_req_duration",
      p95: m.p95_duration_ms ?? 0,
      p50: Number.NaN,
      error_rate: m.error_rate,
      vu_count: m.vus,
    });
  }
  return out;
}
