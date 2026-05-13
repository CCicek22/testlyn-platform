import type { Metadata } from "next";

export const metadata: Metadata = { title: "Changelog" };

const ENTRIES = [
  {
    version: "0.1.0",
    date: "2026-05-12",
    tag: "alpha",
    changes: [
      "Initial Phase 1 vertical slice: load testing end-to-end.",
      "k6 + BQ sidecar integration — 1s aggregated metrics streaming.",
      "Live Recharts dashboard chart on runs page.",
      "Firebase Auth with Google, GitHub, and email/password.",
      "Monaco editor for inline k6 scripts.",
      "Project / test / run CRUD via REST API.",
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
        What&apos;s new in Testlyn. Dates in YYYY-MM-DD.
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
                  <span className="mt-0.5 text-primary" aria-hidden="true">
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
