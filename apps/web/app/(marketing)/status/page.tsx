import type { Metadata } from "next";

export const metadata: Metadata = { title: "Status" };

const SERVICES = [
  { name: "API", status: "operational" },
  { name: "Web dashboard", status: "operational" },
  { name: "Load engine (k6 runner)", status: "operational" },
  { name: "BigQuery streaming", status: "operational" },
  { name: "Authentication (Identity Platform)", status: "operational" },
  { name: "Cloud Storage (reports / scripts)", status: "operational" },
] as const;

type Status = "operational" | "degraded" | "outage";

function StatusBadge({ status }: { status: Status }) {
  const map = {
    operational: { label: "Operational", color: "bg-success" },
    degraded: { label: "Degraded", color: "bg-warn" },
    outage: { label: "Outage", color: "bg-alert" },
  } satisfies Record<Status, { label: string; color: string }>;
  const { label, color } = map[status];
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${color}`} aria-hidden="true" />
      <span className="text-sm text-zinc-600">{label}</span>
    </span>
  );
}

export default function StatusPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-20 sm:px-6">
      <h1 className="mb-2 text-3xl font-bold tracking-tight text-zinc-900">
        System status
      </h1>
      <p className="mb-8 text-zinc-500">
        Real-time status page coming soon. All systems are currently reporting
        operational.
      </p>

      <div className="overflow-hidden rounded-xl border border-zinc-200">
        <div className="divide-y divide-zinc-200">
          {SERVICES.map((svc) => (
            <div
              key={svc.name}
              className="flex items-center justify-between px-4 py-3"
            >
              <span className="text-sm font-medium text-zinc-900">
                {svc.name}
              </span>
              <StatusBadge status={svc.status} />
            </div>
          ))}
        </div>
      </div>

      <p className="mt-6 text-xs text-zinc-400">
        Last checked: {new Date().toISOString()} (static — live status
        monitoring in Phase 1 roadmap).
      </p>
    </div>
  );
}
