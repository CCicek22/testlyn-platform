"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuth } from "@/components/auth/auth-provider";
import { Skeleton } from "@/components/ui/skeleton";
import type { MeResponse } from "@testlyn/shared";

interface InsightsSnapshot {
  id: string | null;
  org_id: string;
  snapshot_time: string;
  p95_latency_ms: number | null;
  a11y_score: number | null;
  open_critical_findings: number | null;
  contract_drift_count: number | null;
  synthetic_data_freshness_h: number | null;
  payload: Record<string, unknown> | null;
}

// R5-C2: Typed key union scoped to the numeric KPI fields on InsightsSnapshot.
// Derived as a pick of the keys whose values are `number | null`, so the
// KpiCard value prop stays correctly typed without any `as` cast.
type KpiKey = Extract<
  keyof InsightsSnapshot,
  | "p95_latency_ms"
  | "a11y_score"
  | "open_critical_findings"
  | "contract_drift_count"
  | "synthetic_data_freshness_h"
>;

interface KpiCardProps {
  label: string;
  value: string | number | null;
  unit?: string;
  accent: string;
  description: string;
}

function KpiCard({ label, value, unit, accent, description }: KpiCardProps) {
  const display = value === null || value === undefined ? "—" : String(value);
  return (
    <div
      className="rounded-xl border bg-zinc-900 p-5 flex flex-col gap-2"
      style={{ borderColor: `${accent}40` }}
    >
      <div
        className="text-xs font-semibold uppercase tracking-widest"
        style={{ color: accent }}
      >
        {label}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-3xl font-bold text-zinc-50 tabular-nums">
          {display}
        </span>
        {unit && value !== null && (
          <span className="text-sm text-zinc-400">{unit}</span>
        )}
      </div>
      <p className="text-xs text-zinc-500">{description}</p>
    </div>
  );
}

const KPI_DEFS: Array<{
  key: KpiKey;
  label: string;
  unit?: string;
  accent: string;
  description: string;
}> = [
  {
    key: "p95_latency_ms",
    label: "p95 Latency",
    unit: "ms",
    accent: "#3730A3",
    description: "95th-percentile response time across all load test runs.",
  },
  {
    key: "a11y_score",
    label: "A11y Score",
    unit: "%",
    accent: "#14B8A6",
    description: "Weighted WCAG compliance score from the latest a11y audit.",
  },
  {
    key: "open_critical_findings",
    label: "Critical Security Findings",
    accent: "#DC2626",
    description: "Open high-risk findings from the most recent ZAP scan.",
  },
  {
    key: "contract_drift_count",
    label: "Contract Drifts",
    accent: "#06B6D4",
    description: "Schema mismatches detected by the latest Schemathesis scan.",
  },
  {
    key: "synthetic_data_freshness_h",
    label: "Data Freshness",
    unit: "h ago",
    accent: "#F59E0B",
    description: "Hours since the last synthetic data generation job completed.",
  },
];

export default function InsightsPage() {
  const { user } = useAuth();

  // R5-C1: Derive org ID from auth context via api.me() instead of hardcoding
  // the placeholder UUID which caused 403/404 for every real user.
  const { data: me } = useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => api.me(),
    enabled: user != null,
    staleTime: 5 * 60_000,
  });

  const orgId = me?.memberships?.[0]?.org_id ?? null;

  const { data: snapshot, isLoading } = useQuery<InsightsSnapshot>({
    queryKey: ["insights", "latest", orgId],
    queryFn: () => api.insights.latest<InsightsSnapshot>(orgId!),
    refetchInterval: 60_000,
    enabled: orgId != null,
  });

  if (!user) {
    return (
      <div className="p-6">
        <p className="text-sm text-zinc-400">Sign in to continue.</p>
      </div>
    );
  }

  if (me != null && orgId == null) {
    return (
      <div className="p-6">
        <p className="text-sm text-zinc-400">
          Select an organization to view insights.
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-zinc-50">Insights</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Cross-product KPIs — refreshed hourly via Cloud Scheduler.
        </p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {KPI_DEFS.map((kpi) => (
            <KpiCard
              key={kpi.key}
              label={kpi.label}
              // R5-C2: snapshot[kpi.key] is typed as number | null via KpiKey —
              // no unsafe `as` cast needed.
              value={snapshot?.[kpi.key] ?? null}
              unit={kpi.unit}
              accent={kpi.accent}
              description={kpi.description}
            />
          ))}
        </div>
      )}

      {snapshot && (
        <p className="text-xs text-zinc-600">
          Last snapshot:{" "}
          {new Date(snapshot.snapshot_time).toLocaleString(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </p>
      )}
    </div>
  );
}
