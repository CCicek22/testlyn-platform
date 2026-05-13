"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Skeleton } from "@/components/ui/skeleton";

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
  key: keyof InsightsSnapshot;
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
  // TODO: replace with real org_id from auth context once org selector lands
  const orgId = "00000000-0000-0000-0000-000000000000";

  const { data: snapshot, isLoading } = useQuery<InsightsSnapshot>({
    queryKey: ["insights", "latest", orgId],
    queryFn: () => api.insights.latest<InsightsSnapshot>(orgId),
    refetchInterval: 60_000,
  });

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
              value={snapshot?.[kpi.key] as number | null ?? null}
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
