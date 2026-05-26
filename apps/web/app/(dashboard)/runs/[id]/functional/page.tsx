"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { getProduct } from "@/lib/products";
import type { TestRun, RunState, FunctionalRunSummary } from "@testlyn/shared";

const PRODUCT = "functional";
const ACCENT = getProduct(PRODUCT).accent; // #7CFFE1

const STATE_STYLES: Record<RunState, string> = {
  queued:    "border-zinc-700 bg-zinc-800 text-zinc-400",
  running:   "border-violet-500/30 bg-violet-500/10 text-violet-400",
  done:      "border-success/30 bg-success/10 text-success",
  error:     "border-alert/30 bg-alert/10 text-alert",
  cancelled: "border-zinc-700 bg-zinc-800 text-zinc-400",
};

function StatCard({ label, value, colorClass }: { label: string; value: string | number; colorClass?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className={`mt-1 font-mono text-2xl font-bold ${colorClass ?? "text-zinc-100"}`}>{value}</p>
    </div>
  );
}

export default function FunctionalRunPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const router = useRouter();

  const { data: run, isLoading, error } = useQuery<TestRun>({
    queryKey: ["run", runId],
    queryFn: () => api.runs.get(runId),
    enabled: !!runId,
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "running" || state === "queued" ? 5000 : false;
    },
  });

  // Summary data — will be populated by W2B backend stream
  const { data: summary } = useQuery<FunctionalRunSummary>({
    queryKey: ["run-summary", runId, PRODUCT],
    queryFn: () => api.runs.summary(runId, PRODUCT) as Promise<FunctionalRunSummary>,
    enabled: !!run && (run.state === "done" || run.state === "error"),
  });

  if (error) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div role="alert" className="rounded-md bg-alert/10 px-4 py-3 text-sm text-alert">
          Failed to load run.
        </div>
      </div>
    );
  }

  const state: RunState = run?.state ?? "queued";

  return (
    <div className="flex flex-col min-h-full" data-product={PRODUCT}>
      {/* Product accent header strip */}
      <div
        className="border-b border-zinc-800 px-6 py-3"
        style={{ borderTopColor: ACCENT, borderTopWidth: 3 }}
      >
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: ACCENT }}>
          Functional Testing
        </span>
      </div>

      <div className="mx-auto w-full max-w-5xl px-6 py-8">
        <button
          onClick={() => router.push("/runs?product=functional")}
          className="mb-4 flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-100"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
          All functional runs
        </button>

        <div className="mb-6 flex items-center gap-3">
          <h1 className="text-xl font-bold tracking-tight text-zinc-100">Run</h1>
          {isLoading ? (
            <Skeleton className="h-5 w-32 bg-zinc-800" />
          ) : (
            <Badge className="border-zinc-700 bg-zinc-800 font-mono text-xs text-zinc-400">{runId}</Badge>
          )}
          {!isLoading && (
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATE_STYLES[state]}`}>
              {state.charAt(0).toUpperCase() + state.slice(1)}
            </span>
          )}
        </div>

        {/* Result summary */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          <StatCard label="Passed"  value={summary?.tests_passed  ?? "—"} colorClass="text-success" />
          <StatCard label="Failed"  value={summary?.tests_failed  ?? "—"} colorClass="text-alert" />
          <StatCard label="Healed"  value={summary?.tests_healed  ?? "—"} colorClass="text-warn" />
        </div>

        {state === "running" || state === "queued" ? (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center">
            <div
              className="mx-auto mb-3 h-2 w-32 animate-pulse rounded-full"
              style={{ backgroundColor: ACCENT }}
              aria-hidden="true"
            />
            <p className="text-sm text-zinc-400">
              {state === "queued" ? "Waiting for runner…" : "Tests running…"}
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
            <h2 className="mb-2 text-sm font-medium text-zinc-300">Test results</h2>
            <p className="text-xs text-zinc-500">
              Per-test breakdown available once the Functional runner (W2B) ships full result streaming.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
