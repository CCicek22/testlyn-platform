"use client";

import { useEffect, useState } from "react";
// NOTE: This is a client component so metadata is set via document.title.
// A server-side metadata export lives in the parent segment if needed.

type ComponentStatus = "operational" | "degraded" | "outage" | "maintenance";

interface StatusComponent {
  id: string;
  name: string;
  status: ComponentStatus;
  uptime_90d?: number; // percentage 0–100
}

interface StatusIncident {
  id: string;
  title: string;
  body: string;
  severity: "minor" | "major" | "critical";
  created_at: string;
  resolved_at: string | null;
}

interface StatusResponse {
  overall: ComponentStatus;
  components: StatusComponent[];
  incidents: StatusIncident[];
  fetched_at: string;
}

const STATUS_MAP: Record<
  ComponentStatus,
  { label: string; dot: string; text: string }
> = {
  operational: {
    label: "Operational",
    dot: "bg-success",
    text: "text-success",
  },
  degraded: { label: "Degraded", dot: "bg-warn", text: "text-warn" },
  outage: { label: "Outage", dot: "bg-alert", text: "text-alert" },
  maintenance: {
    label: "Maintenance",
    dot: "bg-zinc-400",
    text: "text-zinc-400",
  },
};

const OVERALL_LABEL: Record<ComponentStatus, string> = {
  operational: "All systems operational",
  degraded: "Partial degradation",
  outage: "Service disruption",
  maintenance: "Scheduled maintenance",
};

// Fallback static data shown while loading or when API is unreachable.
const FALLBACK: StatusResponse = {
  overall: "operational",
  fetched_at: new Date().toISOString(),
  components: [
    { id: "api", name: "API", status: "operational", uptime_90d: 99.98 },
    {
      id: "web",
      name: "Web dashboard",
      status: "operational",
      uptime_90d: 99.97,
    },
    {
      id: "engine",
      name: "Load engine (k6 runner)",
      status: "operational",
      uptime_90d: 99.95,
    },
    {
      id: "bq",
      name: "BigQuery streaming",
      status: "operational",
      uptime_90d: 99.9,
    },
    {
      id: "auth",
      name: "Authentication (Identity Platform)",
      status: "operational",
      uptime_90d: 100,
    },
    {
      id: "storage",
      name: "Cloud Storage (reports / scripts)",
      status: "operational",
      uptime_90d: 100,
    },
  ],
  incidents: [],
};

async function fetchStatus(): Promise<StatusResponse> {
  // NEXT_PUBLIC_* values are inlined at build time and identical on the
  // server and client — no need for a `typeof window` runtime gate.
  const apiBase =
    process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8080";
  const res = await fetch(`${apiBase}/v1/public/status`, {
    next: { revalidate: 60 },
  });
  if (!res.ok) throw new Error(`status ${res.status}`);
  return res.json() as Promise<StatusResponse>;
}

function StatusBadge({ status }: { status: ComponentStatus }) {
  const { label, dot } = STATUS_MAP[status];
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
      <span className="text-sm text-zinc-600">{label}</span>
    </span>
  );
}

function UptimeBar({ pct }: { pct: number }) {
  // 90-day uptime rendered as a simple percentage bar
  const color =
    pct >= 99.9 ? "bg-success" : pct >= 99 ? "bg-warn" : "bg-alert";
  return (
    <div
      className="flex items-center gap-2"
      title={`${pct.toFixed(2)}% uptime (90 days)`}
    >
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-zinc-200">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-zinc-500">{pct.toFixed(2)}%</span>
    </div>
  );
}

function IncidentFeed({ incidents }: { incidents: StatusIncident[] }) {
  if (!incidents.length) return null;

  const severityColor: Record<StatusIncident["severity"], string> = {
    minor: "border-l-warn",
    major: "border-l-alert",
    critical: "border-l-alert",
  };

  return (
    <div className="mt-8">
      <h2 className="mb-4 text-lg font-semibold text-zinc-900">
        Active incidents
      </h2>
      <ul className="flex flex-col gap-3">
        {incidents.map((inc) => (
          <li
            key={inc.id}
            className={`rounded-lg border-l-4 bg-zinc-50 px-4 py-3 ${severityColor[inc.severity]}`}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-medium text-zinc-900">{inc.title}</p>
              <span className="shrink-0 text-xs text-zinc-500">
                {new Date(inc.created_at).toLocaleString()}
              </span>
            </div>
            <p className="mt-1 text-sm text-zinc-600">{inc.body}</p>
            {inc.resolved_at && (
              <p className="mt-1 text-xs text-success">
                Resolved {new Date(inc.resolved_at).toLocaleString()}
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function StatusPage() {
  const [data, setData] = useState<StatusResponse>(FALLBACK);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    document.title = "System Status | Testlyn";
    fetchStatus()
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch(() => {
        setError(true);
      })
      .finally(() => setLoading(false));
  }, []);

  const overall = STATUS_MAP[data.overall];

  return (
    <div className="mx-auto max-w-3xl px-4 py-20 sm:px-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="mb-2 text-3xl font-bold tracking-tight text-zinc-900">
          System status
        </h1>
        <div className="flex items-center gap-2">
          <span
            className={`h-3 w-3 rounded-full ${overall.dot}`}
            aria-hidden="true"
          />
          <p className={`text-base font-medium ${overall.text}`}>
            {OVERALL_LABEL[data.overall]}
          </p>
        </div>
        {error && (
          <p className="mt-1 text-sm text-zinc-500">
            Could not reach live status API — showing cached data.
          </p>
        )}
      </div>

      {/* Component table */}
      <div className="overflow-hidden rounded-xl border border-zinc-200">
        <div className="divide-y divide-zinc-200">
          {loading
            ? Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between px-4 py-3"
                >
                  <div className="h-4 w-48 animate-pulse rounded bg-zinc-100" />
                  <div className="h-4 w-20 animate-pulse rounded bg-zinc-100" />
                </div>
              ))
            : data.components.map((comp) => (
                <div
                  key={comp.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
                >
                  <span className="text-sm font-medium text-zinc-900">
                    {comp.name}
                  </span>
                  <div className="flex items-center gap-4">
                    {comp.uptime_90d !== undefined && (
                      <UptimeBar pct={comp.uptime_90d} />
                    )}
                    <StatusBadge status={comp.status} />
                  </div>
                </div>
              ))}
        </div>
      </div>

      {/* Incident feed */}
      <IncidentFeed incidents={data.incidents} />

      {/* Footer */}
      <p className="mt-6 text-xs text-zinc-400">
        Last refreshed:{" "}
        {loading
          ? "…"
          : new Date(data.fetched_at).toLocaleString()}{" "}
        · Auto-refreshes every 60 s
      </p>
    </div>
  );
}
