"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useCallback, useRef } from "react";
import { api } from "@/lib/api-client";
import { useSSE } from "@/lib/sse";
import { mapFrameMetrics } from "@/lib/run-stream";
import { LiveLatencyChart } from "@/components/charts/live-latency-chart";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { TestRun, LiveSample, RunStreamFrame, RunState } from "@testlyn/shared";

const TERMINAL_STATES: ReadonlySet<RunState> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

interface RunSummary {
  run_id: string;
  summary_uri: string | null;
  state: RunState;
  error_reason: string | null;
}

const STATE_CONFIG: Record<
  RunState,
  { label: string; color: string; dotColor: string }
> = {
  queued: {
    label: "Queued",
    color: "border-zinc-700 bg-zinc-800 text-zinc-400",
    dotColor: "bg-zinc-500",
  },
  running: {
    label: "Running",
    color: "border-primary/30 bg-primary/10 text-primary",
    dotColor: "bg-primary animate-pulse",
  },
  completed: {
    label: "Completed",
    color: "border-success/30 bg-success/10 text-success",
    dotColor: "bg-success",
  },
  failed: {
    label: "Failed",
    color: "border-alert/30 bg-alert/10 text-alert",
    dotColor: "bg-alert",
  },
  cancelled: {
    label: "Cancelled",
    color: "border-zinc-700 bg-zinc-800 text-zinc-400",
    dotColor: "bg-zinc-500",
  },
};

function RunStateBadge({ state }: { state: RunState }) {
  // Fallback guards against unknown wire values crashing the page.
  const cfg = STATE_CONFIG[state] ?? STATE_CONFIG.queued;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${cfg.color}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${cfg.dotColor}`} aria-hidden="true" />
      {cfg.label}
    </span>
  );
}

function StatCard({ label, value, unit }: { label: string; value: string | number; unit?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 font-mono text-xl font-semibold text-zinc-100">
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-zinc-400">{unit}</span>}
      </p>
    </div>
  );
}

export default function RunPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const router = useRouter();
  const qc = useQueryClient();

  const [samples, setSamples] = useState<LiveSample[]>([]);
  const [liveState, setLiveState] = useState<RunState | null>(null);
  const [sseError, setSseError] = useState<string | null>(null);

  // Fetch initial run metadata
  const {
    data: run,
    isLoading,
    error: runError,
  } = useQuery<TestRun>({
    queryKey: ["run", runId],
    queryFn: () => api.runs.get(runId),
    enabled: !!runId,
    // Poll while running / queued
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "running" || state === "queued" ? 5000 : false;
    },
  });

  // Effective state: SSE state overrides polled state (faster)
  const effectiveState: RunState = liveState ?? run?.state ?? "queued";

  const isTerminal = TERMINAL_STATES.has(effectiveState);

  // For terminal runs opened directly from the run list there is no live SSE
  // stream, so the in-memory `samples` array stays empty. Fetch the persisted
  // run summary so the page reflects the real final state / error instead of
  // hanging on "Waiting for samples…".
  const { data: summary } = useQuery<RunSummary>({
    queryKey: ["run-summary", runId],
    queryFn: () =>
      api.runs.summary(runId, run?.product ?? "load") as Promise<RunSummary>,
    enabled: !!runId && !!run && isTerminal && samples.length === 0,
  });

  // Historical metrics for terminal runs with no live SSE samples. Returns the
  // same LiveSample[] shape the chart + stat cards consume, sourced from the
  // persisted BigQuery rows instead of the live stream.
  const { data: historicalSamples } = useQuery<LiveSample[]>({
    queryKey: ["run-samples", runId],
    queryFn: () => api.runs.samples(runId, run?.product ?? "load"),
    enabled: !!runId && !!run && isTerminal && samples.length === 0,
  });

  // Unified sample source: live SSE samples while running, persisted samples
  // when opening a finished run cold. The chart, stat cards, and summary all
  // derive from this single array.
  const isHistorical = samples.length === 0 && (historicalSamples?.length ?? 0) > 0;
  const effectiveSamples: LiveSample[] =
    samples.length > 0 ? samples : historicalSamples ?? [];

  const streamUrl =
    run && (effectiveState === "running" || effectiveState === "queued")
      ? api.runs.streamUrl(runId)
      : null;

  // Dedupe set + last-seen state for the SSE stream: each frame re-sends the
  // last-60s metric window, and every frame carries `state`.
  const seenTsRef = useRef<Set<string>>(new Set());
  const lastStreamStateRef = useRef<RunState | null>(null);

  const onMessage = useCallback((frame: RunStreamFrame) => {
    const fresh = mapFrameMetrics(frame, seenTsRef.current);
    if (fresh.length > 0) {
      // Cap to a sliding window of the last hour of 1-Hz samples so memory
      // stays bounded on long-running tests.
      setSamples((prev) => [...prev, ...fresh].slice(-3600));
    }
    if (frame.state !== lastStreamStateRef.current) {
      lastStreamStateRef.current = frame.state;
      setLiveState(frame.state);
      void qc.invalidateQueries({ queryKey: ["run", runId] });
    }
  }, [qc, runId]);

  const onSSEError = useCallback(() => {
    setSseError("Live stream disconnected — retrying…");
  }, []);

  // Server sent `event: done` — the run reached a terminal state (or the
  // stream hit its tick cap); refetch the run to pick up the final state.
  // Clear a stale non-terminal live state so it can't mask the polled state
  // (the last tick may have yielded no metrics frame).
  const onDone = useCallback(() => {
    setSseError(null);
    setLiveState((prev) => (prev && TERMINAL_STATES.has(prev) ? prev : null));
    void qc.invalidateQueries({ queryKey: ["run", runId] });
  }, [qc, runId]);

  useSSE<RunStreamFrame>(streamUrl, {
    onMessage,
    onError: onSSEError,
    onDone,
    enabled: !!streamUrl,
  });

  // Cancel run
  const cancelMutation = useMutation({
    mutationFn: () => api.runs.cancel(runId),
    onSuccess: () => {
      setLiveState("cancelled");
      void qc.invalidateQueries({ queryKey: ["run", runId] });
    },
  });

  // Latest sample metrics for stat cards
  const latestSample = effectiveSamples[effectiveSamples.length - 1];

  if (runError) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div role="alert" className="rounded-md bg-alert/10 px-4 py-3 text-sm text-alert">
          Failed to load run.
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <button
            onClick={() => router.back()}
            className="mb-3 flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-100"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
            Back
          </button>

          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold tracking-tight text-zinc-100">
              Run
            </h1>
            <Badge className="border-zinc-700 bg-zinc-800 font-mono text-xs text-zinc-400">
              {runId}
            </Badge>
            {isLoading ? (
              <Skeleton className="h-5 w-20 bg-zinc-800" />
            ) : (
              <RunStateBadge state={effectiveState} />
            )}
          </div>

          {run && (
            <p className="mt-1 text-sm text-zinc-500">
              {run.config.vus} VUs · {run.config.duration_seconds}s ·{" "}
              Started {new Date(run.started_at ?? run.created_at).toLocaleString()}
            </p>
          )}
        </div>

        {(effectiveState === "running" || effectiveState === "queued") && (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => cancelMutation.mutate()}
            disabled={cancelMutation.isPending}
            aria-label="Cancel run"
          >
            {cancelMutation.isPending ? "Cancelling…" : "Cancel run"}
          </Button>
        )}
      </div>

      {/* SSE reconnect notice */}
      {sseError && effectiveState === "running" && (
        <div
          role="status"
          className="mb-4 rounded-md bg-warn/10 px-3 py-2 text-xs text-warn"
        >
          {sseError}
        </div>
      )}

      {/* Live stats */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="p95 latency"
          value={latestSample ? Math.round(latestSample.p95) : "—"}
          unit={latestSample ? "ms" : undefined}
        />
        <StatCard
          label="p50 latency"
          value={
            latestSample && Number.isFinite(latestSample.p50)
              ? Math.round(latestSample.p50)
              : "—"
          }
          unit={latestSample && Number.isFinite(latestSample.p50) ? "ms" : undefined}
        />
        <StatCard
          label="Error rate"
          value={latestSample ? `${(latestSample.error_rate * 100).toFixed(1)}%` : "—"}
        />
        <StatCard
          label="Active VUs"
          value={latestSample ? latestSample.vu_count : run?.config.vus ?? "—"}
        />
      </div>

      {/* Live chart */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-300">
            {isHistorical ? "Latency" : "Live latency"}
            <span className="ml-2 text-xs font-normal text-zinc-500">
              {isHistorical ? "Full run · 1s resolution" : "Last 60 seconds · 1s resolution"}
            </span>
          </h2>
          <span className="text-xs text-zinc-500">
            {effectiveSamples.length} sample
            {effectiveSamples.length !== 1 ? "s" : ""}
          </span>
        </div>
        <LiveLatencyChart
          samples={effectiveSamples}
          windowSize={isHistorical ? effectiveSamples.length : 60}
        />
      </div>

      {/* Summary (post-run) */}
      {isTerminal && (
        <div className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <h2 className="mb-3 text-sm font-medium text-zinc-300">Run summary</h2>

          {effectiveSamples.length > 0 ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <StatCard
                label="Max p95"
                value={Math.round(Math.max(...effectiveSamples.map((s) => s.p95)))}
                unit="ms"
              />
              <StatCard
                label="Avg p95"
                value={Math.round(
                  effectiveSamples.reduce((acc, s) => acc + s.p95, 0) /
                    effectiveSamples.length
                )}
                unit="ms"
              />
              <StatCard
                label="Peak VUs"
                value={Math.max(...effectiveSamples.map((s) => s.vu_count))}
              />
            </div>
          ) : (
            <p className="text-sm text-zinc-400">
              {effectiveState === "failed"
                ? `Run failed${
                    summary?.error_reason ?? run?.error_reason
                      ? `: ${summary?.error_reason ?? run?.error_reason}`
                      : "."
                  }`
                : effectiveState === "cancelled"
                  ? "Run was cancelled."
                  : "Run completed."}
            </p>
          )}

          <p className="mt-4 text-xs text-zinc-500">
            Detailed report generation available in Phase 2 roadmap.
          </p>
        </div>
      )}
    </div>
  );
}
