/**
 * Canned sample data for the interactive product tour.
 * Mimics what a real first load test produces — used as tour fixtures
 * so users see a populated UI before running anything.
 */

export interface SampleMetricRow {
  ts: string; // ISO second
  vus: number;
  rps: number;
  p95_ms: number;
  error_rate: number;
}

/** 60 seconds of synthetic load ramp data. */
export const SAMPLE_LOAD_METRICS: SampleMetricRow[] = Array.from(
  { length: 60 },
  (_, i) => {
    const rampFraction = Math.min(i / 20, 1);
    const vus = Math.round(rampFraction * 50);
    const base_rps = vus * 4;
    const noise = (Math.sin(i * 0.8) + 1) * 0.15 + 1;
    return {
      ts: new Date(Date.now() - (60 - i) * 1000).toISOString(),
      vus,
      rps: Math.round(base_rps * noise),
      p95_ms: Math.round(120 + i * 0.8 + Math.sin(i) * 15),
      error_rate: i > 50 ? 0.002 : 0,
    };
  }
);

export const SAMPLE_RUN_SUMMARY = {
  id: "tour-run-001",
  status: "passed",
  product: "load",
  started_at: new Date(Date.now() - 90_000).toISOString(),
  ended_at: new Date(Date.now() - 30_000).toISOString(),
  peak_vus: 50,
  total_requests: 14400,
  error_rate: 0.0003,
  p50_ms: 87,
  p95_ms: 156,
  p99_ms: 210,
  throughput_rps: 240,
};

export const SAMPLE_TEST = {
  id: "tour-test-001",
  name: "Homepage load test",
  product: "load",
  script: `import http from "k6/http";
import { sleep, check } from "k6";

export const options = {
  vus: 50,
  duration: "60s",
};

export default function () {
  const res = http.get("https://example.com");
  check(res, { "status 200": (r) => r.status === 200 });
  sleep(0.25);
}
`,
};
