import Link from "next/link";
import { HeroChart } from "@/components/charts/hero-chart";

// Value prop data — TODO: replace with real benchmark numbers from production
const STATS = [
  { label: "median cold-start", value: "< 200ms", note: "TODO: real data" },
  { label: "samples streamed per run", value: "3,600+", note: "TODO: real data" },
  { label: "BQ write latency p95", value: "< 800ms", note: "TODO: real data" },
];

const FEATURES = [
  {
    icon: "▶",
    title: "k6-native, zero lock-in",
    body:
      "Paste any k6 script. We run stock grafana/k6 — no proprietary binary, no vendor extension. Your scripts work locally too.",
  },
  {
    icon: "⚡",
    title: "Live metrics in < 5s",
    body:
      "The BQ sidecar streams 1-second aggregates during the run. The dashboard chart populates within 5 seconds of launch.",
  },
  {
    icon: "📊",
    title: "p95 / p99 / error rate",
    body:
      "Every run records p50, p95, p99 latency plus error rate per second. Query your full history in BigQuery.",
  },
  {
    icon: "🔑",
    title: "API-first",
    body:
      "Every action in the UI is also available via a REST API. Trigger runs from CI/CD with a single curl.",
  },
];

export default function LandingPage() {
  return (
    <>
      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-4 pb-16 pt-20 sm:px-6 sm:pt-28">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          Phase 1 — Load Testing now in beta
        </div>

        <h1 className="mb-4 max-w-3xl font-display text-4xl font-bold tracking-tight text-zinc-900 sm:text-5xl lg:text-6xl">
          Load test your API{" "}
          <span className="text-primary">like you mean it.</span>
        </h1>

        <p className="mb-8 max-w-2xl text-lg text-zinc-500">
          Testlyn runs k6 load tests on GCP, streams live p95/error metrics to
          your dashboard, and stores every sample in BigQuery. No black boxes.
          Dev-to-dev, real numbers only.
        </p>

        <div className="flex flex-wrap gap-3">
          <Link
            href="/signup"
            className="inline-flex h-10 items-center rounded-md bg-primary px-6 text-sm font-medium text-white hover:bg-primary-600 transition-colors"
          >
            Start free — no card required
          </Link>
          <Link
            href="/docs"
            className="inline-flex h-10 items-center rounded-md border border-zinc-300 bg-white px-6 text-sm font-medium text-zinc-700 hover:bg-zinc-50 transition-colors"
          >
            Read the docs
          </Link>
        </div>

        {/* Hero chart (live-looking, SVG only) */}
        <div className="mt-14">
          <HeroChart />
        </div>
      </section>

      {/* ── Stats ─────────────────────────────────────────────── */}
      <section className="border-y border-zinc-200 bg-zinc-50 py-12">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <dl className="grid grid-cols-1 gap-8 sm:grid-cols-3">
            {STATS.map((s) => (
              <div key={s.label} className="text-center">
                <dt className="text-sm text-zinc-500">{s.label}</dt>
                <dd className="mt-1 font-mono text-3xl font-bold text-zinc-900">
                  {s.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ── Features ──────────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <h2 className="mb-12 text-2xl font-bold tracking-tight text-zinc-900 sm:text-3xl">
          Everything you need to test at scale.
        </h2>
        <div className="grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <article key={f.title} className="flex flex-col gap-3">
              <span className="text-2xl" aria-hidden="true">{f.icon}</span>
              <h3 className="font-semibold text-zinc-900">{f.title}</h3>
              <p className="text-sm leading-relaxed text-zinc-500">{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ── CTA ───────────────────────────────────────────────── */}
      <section className="border-t border-zinc-200 bg-zinc-50 py-16">
        <div className="mx-auto max-w-2xl px-4 text-center sm:px-6">
          <h2 className="mb-4 text-2xl font-bold tracking-tight text-zinc-900">
            Start in minutes. Ship with data.
          </h2>
          <p className="mb-6 text-zinc-500">
            Free tier: 5 runs/month, up to 50 VUs, 5 minutes each. No card needed.
          </p>
          <Link
            href="/signup"
            className="inline-flex h-10 items-center rounded-md bg-primary px-8 text-sm font-medium text-white hover:bg-primary-600 transition-colors"
          >
            Create free account
          </Link>
        </div>
      </section>
    </>
  );
}
