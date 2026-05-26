"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Skeleton } from "@/components/ui/skeleton";

interface SyntheticDataJob {
  job_id: string;
  product: "synthetic_data";
  status: "queued" | "running" | "completed" | "failed";
  dump_gcs_uri: string | null;
  rows_inserted: number | null;
  message: string | null;
}

const STATUS_COLOR: Record<SyntheticDataJob["status"], string> = {
  queued: "border-zinc-700 bg-zinc-800 text-zinc-400",
  running: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  completed: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  failed: "border-red-500/30 bg-red-500/10 text-red-400",
};

export default function SyntheticDataRunPage() {
  const { id } = useParams<{ id: string }>();

  const { data: job, isLoading } = useQuery<SyntheticDataJob>({
    queryKey: ["synthetic-data-job", id],
    queryFn: () => api.syntheticData.getJob<SyntheticDataJob>(id),
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
          style={{ backgroundColor: "#FFD166" }}
          aria-hidden="true"
        />
        <h1 className="text-xl font-bold text-zinc-50">Synthetic Data Job</h1>
        {job && (
          <span
            className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_COLOR[job.status]}`}
          >
            {job.status}
          </span>
        )}
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 space-y-4">
        <div>
          <p className="text-xs text-zinc-500 uppercase tracking-wider">Job ID</p>
          <p className="mt-1 font-mono text-sm text-zinc-300">{id}</p>
        </div>

        {job?.dump_gcs_uri && (
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-wider">Output URI</p>
            <p className="mt-1 font-mono text-sm text-zinc-300 break-all">
              {job.dump_gcs_uri}
            </p>
          </div>
        )}

        {job?.rows_inserted !== null && job?.rows_inserted !== undefined && (
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-wider">Rows Inserted</p>
            <p className="mt-1 text-2xl font-bold text-zinc-50 tabular-nums">
              {job.rows_inserted.toLocaleString()}
            </p>
          </div>
        )}

        {job?.message && (
          <div className="rounded-lg bg-zinc-800 px-3 py-2 text-xs text-zinc-400 font-mono">
            {job.message}
          </div>
        )}

        {!job && (
          <p className="text-sm text-zinc-400">
            Job details not found. The job may still be initializing.
          </p>
        )}
      </div>
    </div>
  );
}
