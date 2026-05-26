"use client";

import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { AuditLogEntry, AuditListParams } from "@/lib/api-client";
import { useAuth } from "@/components/auth/auth-provider";
import type { MeResponse } from "@testlyn/shared";

// ─── Constants ────────────────────────────────────────────────────────────────

const KNOWN_ACTIONS = [
  "org.created",
  "org.updated",
  "org.deleted",
  "project.created",
  "project.updated",
  "project.deleted",
  "target.created",
  "target.updated",
  "target.deleted",
  "test.created",
  "test.updated",
  "test.deleted",
  "test_run.started",
  "test_run.completed",
  "test_run.failed",
  "member.invited",
  "member.removed",
  "member.role_changed",
  "audit_sink.created",
  "audit_sink.deleted",
] as const;

const PAGE_LIMIT = 50;

// ─── Filter chip ──────────────────────────────────────────────────────────────

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "inline-flex items-center rounded-full px-3 py-1 text-xs font-medium transition-colors",
        active
          ? "bg-primary text-[#031111]"
          : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

// ─── Action badge ─────────────────────────────────────────────────────────────

function ActionBadge({ action }: { action: string }) {
  const color =
    action.includes("delete") || action.includes("removed") || action.includes("failed")
      ? "bg-red-500/15 text-red-400"
      : action.includes("created") || action.includes("started") || action.includes("invited")
        ? "bg-emerald-500/15 text-emerald-400"
        : action.includes("updated") || action.includes("changed") || action.includes("completed")
          ? "bg-primary/15 text-primary"
          : "bg-zinc-500/15 text-zinc-400";

  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 font-mono text-xs ${color}`}
    >
      {action}
    </span>
  );
}

// ─── Row ──────────────────────────────────────────────────────────────────────

function AuditRow({ entry }: { entry: AuditLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetails = entry.before != null || entry.after != null;
  // Stable ID for aria-controls linkage between toggle button and detail row.
  const detailRowId = `audit-detail-${entry.id}`;

  return (
    <>
      {/*
        R5-C3: <tr> is not an interactive element — aria-expanded + onClick on
        <tr> is invalid ARIA and unreachable by keyboard. The expand toggle is
        now a <button> inside the last <td> so it gets focus, Enter/Space, and
        correct aria-expanded / aria-controls attributes.
      */}
      <tr className="border-b border-zinc-800/60 text-sm">
        <td className="whitespace-nowrap py-2.5 pl-4 pr-3 text-zinc-500">
          {new Date(entry.created_at).toLocaleString()}
        </td>
        <td className="px-3 py-2.5">
          <ActionBadge action={entry.action} />
        </td>
        <td className="px-3 py-2.5 text-zinc-300">
          {entry.resource_type}
        </td>
        <td className="px-3 py-2.5 font-mono text-xs text-zinc-500">
          {entry.resource_id ?? "—"}
        </td>
        <td className="px-3 py-2.5 font-mono text-xs text-zinc-500">
          {entry.actor_user_id ?? "system"}
        </td>
        <td className="py-2.5 pl-3 pr-4 text-zinc-600">
          <div className="flex items-center justify-between gap-2">
            <span>{entry.ip ?? "—"}</span>
            {hasDetails && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                aria-expanded={expanded}
                aria-controls={detailRowId}
                aria-label="Toggle row details"
                className="flex-shrink-0 rounded p-0.5 text-zinc-500 hover:bg-zinc-700 hover:text-zinc-200 focus:outline-none focus-visible:ring-1 focus-visible:ring-primary"
              >
                <svg
                  className={[
                    "h-3.5 w-3.5 transition-transform",
                    expanded ? "rotate-180" : "",
                  ].join(" ")}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </button>
            )}
          </div>
        </td>
      </tr>
      {expanded && hasDetails && (
        <tr id={detailRowId} className="border-b border-zinc-800/60 bg-zinc-900">
          <td colSpan={6} className="px-4 py-3">
            <div className="grid gap-3 sm:grid-cols-2">
              {entry.before != null && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">Before</p>
                  <pre className="overflow-auto rounded bg-zinc-950 p-2 text-xs text-zinc-300">
                    {JSON.stringify(entry.before, null, 2)}
                  </pre>
                </div>
              )}
              {entry.after != null && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">After</p>
                  <pre className="overflow-auto rounded bg-zinc-950 p-2 text-xs text-zinc-300">
                    {JSON.stringify(entry.after, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ─── Export helpers ───────────────────────────────────────────────────────────

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AuditLogPage() {
  const { user } = useAuth();
  const [actionFilter, setActionFilter] = useState<string | null>(null);
  const [fromDt, setFromDt] = useState("");
  const [toDt, setToDt] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [exporting, setExporting] = useState<"csv" | "json" | null>(null);

  // Resolve org id from auth context via /v1/me — never hardcode.
  const { data: me } = useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => api.me(),
    enabled: user != null,
    staleTime: 5 * 60_000,
  });
  const orgId = me?.memberships?.[0]?.org_id ?? null;

  const params: AuditListParams = {
    limit: PAGE_LIMIT,
    ...(actionFilter ? { action: actionFilter } : {}),
    ...(fromDt ? { from_dt: fromDt } : {}),
    ...(toDt ? { to_dt: toDt } : {}),
    ...(cursor ? { cursor } : {}),
  };

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["audit-log", orgId, params],
    queryFn: () => api.audit.list(orgId!, params),
    enabled: orgId != null,
  });

  const handleExport = useCallback(
    async (format: "csv" | "json") => {
      if (orgId == null) return;
      setExporting(format);
      try {
        const exportParams = {
          ...(actionFilter ? { action: actionFilter } : {}),
          ...(fromDt ? { from_dt: fromDt } : {}),
          ...(toDt ? { to_dt: toDt } : {}),
          limit: 5000,
        };
        const res =
          format === "csv"
            ? await api.audit.exportCsv(orgId, exportParams)
            : await api.audit.exportJson(orgId, exportParams);
        const blob = await res.blob();
        const ts = new Date().toISOString().slice(0, 10);
        triggerDownload(blob, `audit-log-${ts}.${format}`);
      } finally {
        setExporting(null);
      }
    },
    [actionFilter, fromDt, toDt, orgId]
  );

  const entries = data?.items ?? [];
  const nextCursor = data?.cursor ?? null;

  function resetFilters() {
    setActionFilter(null);
    setFromDt("");
    setToDt("");
    setCursor(null);
  }

  if (orgId == null) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-8">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
          Audit Log
        </h1>
        <p className="mt-4 text-sm text-zinc-500">
          {me == null ? "Loading organization…" : "No organization available."}
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
            Audit Log
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            All organisation events — admin access only.
          </p>
        </div>

        {/* Export buttons */}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void handleExport("csv")}
            disabled={exporting != null}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
            </svg>
            {exporting === "csv" ? "Exporting…" : "Export CSV"}
          </button>
          <button
            type="button"
            onClick={() => void handleExport("json")}
            disabled={exporting != null}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
            </svg>
            {exporting === "json" ? "Exporting…" : "Export JSON"}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-6 space-y-3">
        {/* Action chips */}
        <div className="flex flex-wrap gap-2">
          <FilterChip
            label="All actions"
            active={actionFilter == null}
            onClick={() => { setActionFilter(null); setCursor(null); }}
          />
          {KNOWN_ACTIONS.map((a) => (
            <FilterChip
              key={a}
              label={a}
              active={actionFilter === a}
              onClick={() => { setActionFilter(a); setCursor(null); }}
            />
          ))}
        </div>

        {/* Date range */}
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-zinc-400">
            From
            <input
              type="datetime-local"
              value={fromDt}
              onChange={(e) => { setFromDt(e.target.value); setCursor(null); }}
              className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-400">
            To
            <input
              type="datetime-local"
              value={toDt}
              onChange={(e) => { setToDt(e.target.value); setCursor(null); }}
              className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </label>
          {(actionFilter != null || fromDt || toDt) && (
            <button
              type="button"
              onClick={resetFilters}
              className="text-xs text-zinc-500 underline hover:text-zinc-300"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-zinc-800">
        <table className="w-full min-w-[720px] text-left">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/60">
              <th className="py-2.5 pl-4 pr-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Timestamp
              </th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Action
              </th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Resource
              </th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Resource ID
              </th>
              <th className="px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Actor
              </th>
              <th className="py-2.5 pl-3 pr-4 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                IP
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td colSpan={6} className="py-12 text-center text-sm text-zinc-500">
                  Loading…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={6} className="py-12 text-center text-sm text-red-400">
                  {error instanceof Error ? error.message : "Failed to load audit log"}
                </td>
              </tr>
            )}
            {!isLoading && !isError && entries.length === 0 && (
              <tr>
                <td colSpan={6} className="py-12 text-center text-sm text-zinc-500">
                  No events match the current filters.
                </td>
              </tr>
            )}
            {entries.map((entry) => (
              <AuditRow key={entry.id} entry={entry} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="mt-4 flex items-center justify-between text-sm text-zinc-400">
        <span>
          {entries.length} event{entries.length !== 1 ? "s" : ""}
          {entries.length === PAGE_LIMIT ? "+" : ""}
        </span>
        <div className="flex gap-2">
          {cursor != null && (
            <button
              type="button"
              onClick={() => setCursor(null)}
              className="rounded border border-zinc-700 px-3 py-1.5 text-xs hover:bg-zinc-800"
            >
              First page
            </button>
          )}
          {nextCursor != null && (
            <button
              type="button"
              onClick={() => setCursor(nextCursor)}
              className="rounded border border-zinc-700 px-3 py-1.5 text-xs hover:bg-zinc-800"
            >
              Next page
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
