"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Skeleton } from "@/components/ui/skeleton";

interface ZapFinding {
  plugin_id: string;
  alert: string;
  risk: "high" | "medium" | "low" | "informational";
  confidence: "high" | "medium" | "low";
  url: string;
  description: string;
  solution: string | null;
  reference: string | null;
}

interface SecurityScan {
  scan_id: string;
  product: "security";
  status: "queued" | "running" | "completed" | "failed";
  scan_kind: "baseline" | "full";
  findings_count: number;
  findings: ZapFinding[];
  report_gcs_uri: string | null;
  message: string | null;
}

const STATUS_COLOR: Record<SecurityScan["status"], string> = {
  queued: "border-zinc-700 bg-zinc-800 text-zinc-400",
  running: "border-red-500/30 bg-red-500/10 text-red-400",
  completed: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  failed: "border-red-600/40 bg-red-600/10 text-red-400",
};

const RISK_COLOR: Record<ZapFinding["risk"], string> = {
  high: "text-red-400 border-red-500/40 bg-red-500/10",
  medium: "text-amber-400 border-amber-500/40 bg-amber-500/10",
  low: "text-yellow-400 border-yellow-500/40 bg-yellow-500/10",
  informational: "text-zinc-400 border-zinc-700 bg-zinc-800",
};

export default function SecurityRunPage() {
  const { id } = useParams<{ id: string }>();

  const { data: scan, isLoading } = useQuery<SecurityScan>({
    queryKey: ["security-scan", id],
    queryFn: () => api.security.getScan<SecurityScan>(id),
    refetchInterval: (q) =>
      q.state.data?.status === "running" || q.state.data?.status === "queued"
        ? 3000
        : false,
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <div
          className="h-3 w-3 rounded-full"
          style={{ backgroundColor: "#FF4D6D" }}
          aria-hidden="true"
        />
        <h1 className="text-xl font-bold text-zinc-50">Security Scan</h1>
        {scan && (
          <>
            <span
              className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_COLOR[scan.status]}`}
            >
              {scan.status}
            </span>
            <span className="inline-flex items-center rounded-full border border-zinc-700 bg-zinc-800 px-2.5 py-0.5 text-xs text-zinc-400">
              {scan.scan_kind}
            </span>
          </>
        )}
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 space-y-4">
        <div>
          <p className="text-xs text-zinc-500 uppercase tracking-wider">Scan ID</p>
          <p className="mt-1 font-mono text-sm text-zinc-300">{id}</p>
        </div>

        {scan && (
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-wider">
              Total Findings
            </p>
            <p
              className="mt-1 text-3xl font-bold tabular-nums"
              style={{ color: scan.findings_count > 0 ? "#FF4D6D" : "#5CFF93" }}
            >
              {scan.findings_count}
            </p>
          </div>
        )}

        {scan?.message && (
          <div className="rounded-lg bg-zinc-800 px-3 py-2 text-xs text-zinc-400 font-mono">
            {scan.message}
          </div>
        )}

        {scan && scan.findings.length > 0 && (
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-wider mb-2">
              Findings
            </p>
            <div className="space-y-2">
              {scan.findings.map((f, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-3 space-y-2"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${RISK_COLOR[f.risk]}`}
                    >
                      {f.risk}
                    </span>
                    <span className="text-sm font-medium text-zinc-200">
                      {f.alert}
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400 font-mono break-all">{f.url}</p>
                  <p className="text-xs text-zinc-500">{f.description}</p>
                  {f.solution && (
                    <p className="text-xs text-emerald-400">Fix: {f.solution}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {!scan && (
          <p className="text-sm text-zinc-400">
            Scan details not found. The scan may still be initializing.
          </p>
        )}
      </div>
    </div>
  );
}
