"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Skeleton } from "@/components/ui/skeleton";

interface DriftFinding {
  method: string;
  path: string;
  status_code: number;
  failure_reason: string;
  response_snippet: string | null;
}

interface ContractScan {
  scan_id: string;
  product: "api_contract";
  status: "queued" | "running" | "completed" | "failed";
  drift_count: number;
  findings: DriftFinding[];
  report_gcs_uri: string | null;
  message: string | null;
}

const STATUS_COLOR: Record<ContractScan["status"], string> = {
  queued: "border-zinc-700 bg-zinc-800 text-zinc-400",
  running: "border-cyan-500/30 bg-cyan-500/10 text-cyan-400",
  completed: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  failed: "border-red-500/30 bg-red-500/10 text-red-400",
};

export default function ApiContractRunPage() {
  const { id } = useParams<{ id: string }>();

  const { data: scan, isLoading } = useQuery<ContractScan>({
    queryKey: ["contract-scan", id],
    queryFn: () => api.apiContract.getScan<ContractScan>(id),
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
          style={{ backgroundColor: "#06B6D4" }}
          aria-hidden="true"
        />
        <h1 className="text-xl font-bold text-zinc-50">API Contract Scan</h1>
        {scan && (
          <span
            className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_COLOR[scan.status]}`}
          >
            {scan.status}
          </span>
        )}
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 space-y-4">
        <div>
          <p className="text-xs text-zinc-500 uppercase tracking-wider">Scan ID</p>
          <p className="mt-1 font-mono text-sm text-zinc-300">{id}</p>
        </div>

        {scan && (
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-wider">Drift Count</p>
            <p
              className="mt-1 text-3xl font-bold tabular-nums"
              style={{ color: scan.drift_count > 0 ? "#06B6D4" : "#10B981" }}
            >
              {scan.drift_count}
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
            <p className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Findings</p>
            <div className="space-y-2">
              {scan.findings.map((f, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 space-y-1"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-cyan-400">
                      {f.method}
                    </span>
                    <span className="font-mono text-xs text-zinc-300">{f.path}</span>
                    <span className="text-xs text-zinc-500">HTTP {f.status_code}</span>
                  </div>
                  <p className="text-xs text-zinc-400">{f.failure_reason}</p>
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
