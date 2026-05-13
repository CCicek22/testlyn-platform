import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Changelog",
  description: "What's new in Testlyn. Real version numbers, real dates.",
};

const ENTRIES = [
  {
    version: "0.1.0",
    date: "2026-05-12",
    tag: "alpha",
    changes: [
      "Phase 1 load testing live — end-to-end vertical slice.",
      "Stock grafana/k6 runner on GCP Cloud Run Jobs — no proprietary binary, AGPL-safe.",
      "Python BQ sidecar: 1-second p50/p95/p99 + error rate aggregates streamed to BigQuery.",
      "Live Recharts dashboard chart: data appears within 5s of run start.",
      "Firebase Auth: Google, GitHub, and email/password flows.",
      "Monaco editor for inline k6 script authoring.",
      "Project / test / test_run CRUD via REST API (FastAPI + SQLAlchemy 2 async).",
      "Alembic migrations for Postgres schema (Cloud SQL).",
      "Quota enforcement: Free tier capped at 50 VUs, 5 min, 5 runs/month.",
      "PDF report stub: run summary exported from WeasyPrint pipeline.",
      "Stripe Checkout integration in progress (CTAs disabled).",
      "Terraform IaC: Cloud Run, Cloud SQL, BigQuery, Cloud Tasks, GCS buckets.",
      "GitHub Actions CI with per-app pipelines and Cloud Build integration.",
      "Marketing pages: homepage, pricing, docs, blog, changelog, status.",
    ],
  },
] as const;

export default function ChangelogPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-20 sm:px-6">
      <h1 className="mb-2 text-3xl font-bold tracking-tight text-zinc-900">
        Changelog
      </h1>
      <p className="mb-10 text-zinc-500">
        What&apos;s new in Testlyn. Dates in YYYY-MM-DD. No marketing spin.
      </p>

      <div className="space-y-10">
        {ENTRIES.map((entry) => (
          <article key={entry.version} aria-labelledby={`v${entry.version}`}>
            <header className="mb-4 flex items-center gap-3">
              <h2
                id={`v${entry.version}`}
                className="font-mono text-lg font-semibold text-zinc-900"
              >
                v{entry.version}
              </h2>
              <span className="rounded-full border border-primary/30 bg-primary/5 px-2 py-0.5 text-xs font-medium text-primary">
                {entry.tag}
              </span>
              <time
                dateTime={entry.date}
                className="ml-auto font-mono text-xs text-zinc-400"
              >
                {entry.date}
              </time>
            </header>
            <ul className="space-y-2 text-sm text-zinc-600">
              {entry.changes.map((c) => (
                <li key={c} className="flex items-start gap-2">
                  <span
                    className="mt-0.5 shrink-0 text-primary"
                    aria-hidden="true"
                  >
                    +
                  </span>
                  {c}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </div>
  );
}
