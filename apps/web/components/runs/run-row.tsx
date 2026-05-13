"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";
import { getProduct, type Product } from "@/lib/products";
import type { RunState, TestRun } from "@testlyn/shared";

// ─── State badge ──────────────────────────────────────────────────────────────

const STATE_STYLES: Record<RunState, { dot: string; text: string; bg: string }> = {
  queued:    { dot: "bg-zinc-500",                text: "text-zinc-400",   bg: "bg-zinc-800/60" },
  running:   { dot: "bg-primary animate-pulse",   text: "text-primary",    bg: "bg-primary/10" },
  done:      { dot: "bg-success",                 text: "text-success",    bg: "bg-success/10" },
  error:     { dot: "bg-alert",                   text: "text-alert",      bg: "bg-alert/10" },
  cancelled: { dot: "bg-zinc-500",                text: "text-zinc-400",   bg: "bg-zinc-800/60" },
};

function StateBadge({ state }: { state: RunState }) {
  const s = STATE_STYLES[state];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        s.bg,
        s.text
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} aria-hidden="true" />
      {state.charAt(0).toUpperCase() + state.slice(1)}
    </span>
  );
}

// ─── Per-product extra cells ──────────────────────────────────────────────────

function LoadCells({ run }: { run: TestRun & { p95_ms?: number; error_rate?: number } }) {
  return (
    <>
      <td className="px-4 py-3 font-mono text-sm text-zinc-300">
        {run.p95_ms != null ? `${run.p95_ms} ms` : "—"}
      </td>
      <td className="px-4 py-3 font-mono text-sm text-zinc-300">
        {run.error_rate != null ? `${(run.error_rate * 100).toFixed(1)}%` : "—"}
      </td>
    </>
  );
}

function FunctionalCells({
  run,
}: {
  run: TestRun & { tests_passed?: number; tests_failed?: number; tests_healed?: number };
}) {
  return (
    <>
      <td className="px-4 py-3 text-sm">
        <span className="text-success">{run.tests_passed ?? "—"} passed</span>
        {" / "}
        <span className="text-alert">{run.tests_failed ?? "—"} failed</span>
        {" / "}
        <span className="text-warn">{run.tests_healed ?? "—"} healed</span>
      </td>
    </>
  );
}

function A11yCells({
  run,
}: {
  run: TestRun & {
    urls_scanned?: number;
    violations_critical?: number;
    violations_serious?: number;
    violations_moderate?: number;
    violations_minor?: number;
  };
}) {
  return (
    <>
      <td className="px-4 py-3 font-mono text-sm text-zinc-300">
        {run.urls_scanned ?? "—"}
      </td>
      <td className="px-4 py-3 text-sm text-zinc-300">
        <span className="text-alert">{run.violations_critical ?? 0} crit</span>
        {" · "}
        <span className="text-warn">{run.violations_serious ?? 0} serious</span>
        {" · "}
        {run.violations_moderate ?? 0} mod
        {" · "}
        {run.violations_minor ?? 0} minor
      </td>
    </>
  );
}

// ─── Shared row ───────────────────────────────────────────────────────────────

type AugmentedRun = TestRun & {
  // load
  p95_ms?: number;
  error_rate?: number;
  // functional
  tests_passed?: number;
  tests_failed?: number;
  tests_healed?: number;
  // a11y
  urls_scanned?: number;
  violations_critical?: number;
  violations_serious?: number;
  violations_moderate?: number;
  violations_minor?: number;
};

export function RunRow({ run, product }: { run: AugmentedRun; product: Product }) {
  const meta = getProduct(product);
  const durationMs =
    run.started_at && run.finished_at
      ? new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
      : null;
  const durationStr =
    durationMs != null ? `${Math.round(durationMs / 1000)}s` : "—";

  const detailHref = `/runs/${run.id}/${product}`;

  return (
    <tr className="border-b border-zinc-800 transition-colors hover:bg-zinc-900/60">
      {/* Accent strip */}
      <td className="w-1 px-0 py-0">
        <div
          className="h-full w-1 rounded-l-sm"
          style={{ backgroundColor: meta.accent }}
          aria-hidden="true"
        />
      </td>

      <td className="px-4 py-3">
        <Link
          href={detailHref}
          className="font-mono text-xs text-zinc-400 hover:text-zinc-100"
        >
          {run.id.slice(0, 8)}
        </Link>
      </td>

      <td className="px-4 py-3 text-sm text-zinc-300">
        {run.started_at
          ? new Date(run.started_at).toLocaleString()
          : new Date(run.created_at).toLocaleString()}
      </td>

      <td className="px-4 py-3 font-mono text-sm text-zinc-300">{durationStr}</td>

      {product === "load" && <LoadCells run={run} />}
      {product === "functional" && <FunctionalCells run={run} />}
      {product === "a11y" && <A11yCells run={run} />}

      <td className="px-4 py-3">
        <StateBadge state={run.state} />
      </td>

      <td className="px-4 py-3">
        <Link
          href={detailHref}
          className="text-xs text-zinc-500 hover:text-zinc-100"
          aria-label={`View run ${run.id}`}
        >
          View
        </Link>
      </td>
    </tr>
  );
}
