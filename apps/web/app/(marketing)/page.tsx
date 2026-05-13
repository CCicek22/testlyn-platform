import type { Metadata } from "next";
import Link from "next/link";
import { HeroChart } from "@/components/charts/hero-chart";

export const metadata: Metadata = {
  title: "Testlyn — Load testing that lives where your code does",
  description:
    "Run k6 with native BigQuery streaming, live charts, and AI bottleneck explanations — without the AGPL surface.",
};

const HOW_IT_WORKS = [
  {
    step: "01",
    title: "Write a k6 script",
    description:
      "Paste any valid k6 script into the Monaco editor. No proprietary extensions, no custom DSL. If it runs locally, it runs here.",
    code: `import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  vus: 100,
  duration: '5m',
};

export default function () {
  http.get('https://your-api.example.com/');
  sleep(1);
}`,
  },
  {
    step: "02",
    title: "Run on Testlyn",
    description:
      "Hit Run. We spin up stock grafana/k6 on GCP, start the BQ sidecar, and stream 1-second aggregates to your dashboard in real time.",
    code: `# What happens under the hood:
k6 run --out json=/tmp/metrics.jsonl test.js

# Python sidecar tails the output:
# → parses k6 JSON format
# → aggregates p50/p95/p99 per second
# → streams rows to BigQuery`,
  },
  {
    step: "03",
    title: "Read the AI summary",
    description:
      "Each morning, Gemini analyzes your last 24 hours of runs and emails you a plain-English bottleneck report. No dashboard babysitting.",
    code: `Subject: Testlyn digest — 2026-05-12

production-stress-v3 (500 VUs, 10 min)
  p95: 340ms peak at minute 6
  Spike correlates with error rate jump to 28%
  Likely cause: connection pool exhaustion at
  /api/orders under sustained concurrency.
  Recommendation: increase pool size or add
  circuit breaker before next test.`,
  },
] as const;

const WHY_CARDS = [
  {
    title: "Live BigQuery metrics",
    body: "Every sample lands in your BigQuery dataset. No Grafana Cloud lock-in, no proprietary format. Query your own data with SQL.",
    accent: "border-primary/30",
    label: "No lock-in",
  },
  {
    title: "Daily AI digest",
    body: "Gemini reads your last 24 hours of runs each morning and sends a plain-English bottleneck summary. Opt out anytime.",
    accent: "border-success/30",
    label: "Gemini-powered",
  },
  {
    title: "k6 unmodified — AGPL-safe",
    body: "We run the official grafana/k6 image unchanged. Your scripts need zero modification. Legal team sleeps soundly.",
    accent: "border-warn/30",
    label: "AGPL-safe",
  },
  {
    title: "Real pricing, no sales call",
    body: "Free tier up to 50 VUs. Paid tiers with published prices. Enterprise gets a contact form, not a gated demo.",
    accent: "border-alert/30",
    label: "Transparent",
  },
] as const;

export default function LandingPage() {
  return (
    <>
      {/* ── Hero ─────────────────────────────────────────────── */}
      {/* LCP target: h1 text is SSR-rendered, no client-only gate */}
      <section className="mx-auto max-w-6xl px-4 pb-16 pt-20 sm:px-6 sm:pt-28">
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
          Phase 1 open — Load Testing
        </div>

        <h1 className="mb-4 max-w-3xl font-display text-4xl font-bold tracking-tight text-zinc-900 sm:text-5xl lg:text-6xl">
          Load testing that lives{" "}
          <span className="text-primary">where your code does.</span>
        </h1>

        <p className="mb-8 max-w-2xl text-lg leading-relaxed text-zinc-500">
          Run k6 with native BigQuery streaming, live charts, and AI bottleneck
          explanations — without the AGPL surface.
        </p>

        <div className="flex flex-wrap gap-3">
          <Link
            href="/signup"
            className="inline-flex h-10 items-center rounded-md bg-primary px-6 text-sm font-medium text-white transition-colors hover:bg-indigo-800"
          >
            Start free — no card required
          </Link>
          <Link
            href="/docs"
            className="inline-flex h-10 items-center rounded-md border border-zinc-300 bg-white px-6 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50"
          >
            Read the docs
          </Link>
        </div>

        {/* Hero chart — static SVG, no client-only JS gating LCP */}
        <div className="mt-14">
          <HeroChart />
        </div>
      </section>

      {/* ── How it works ──────────────────────────────────────── */}
      <section className="border-t border-zinc-200 bg-zinc-50 py-20">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <h2 className="mb-3 text-2xl font-bold tracking-tight text-zinc-900 sm:text-3xl">
            How it works
          </h2>
          <p className="mb-12 text-zinc-500">Three steps. No black boxes.</p>

          <div className="grid grid-cols-1 gap-10 lg:grid-cols-3">
            {HOW_IT_WORKS.map((item) => (
              <article key={item.step} className="flex flex-col gap-4">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs font-semibold text-primary">
                    {item.step}
                  </span>
                  <h3 className="font-semibold text-zinc-900">{item.title}</h3>
                </div>
                <p className="text-sm leading-relaxed text-zinc-500">
                  {item.description}
                </p>
                <pre className="overflow-x-auto rounded-lg bg-zinc-900 p-4 text-xs leading-relaxed text-zinc-300">
                  <code className="font-mono">{item.code}</code>
                </pre>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ── Why Testlyn ───────────────────────────────────────── */}
      <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <h2 className="mb-3 text-2xl font-bold tracking-tight text-zinc-900 sm:text-3xl">
          Why Testlyn
        </h2>
        <p className="mb-12 text-zinc-500">
          No fluff. Here is what you actually get.
        </p>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {WHY_CARDS.map((card) => (
            <article
              key={card.title}
              className={`flex flex-col gap-3 rounded-xl border ${card.accent} bg-white p-6`}
            >
              <span className="inline-block rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-600">
                {card.label}
              </span>
              <h3 className="font-semibold text-zinc-900">{card.title}</h3>
              <p className="text-sm leading-relaxed text-zinc-500">{card.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ── Bottom CTA ────────────────────────────────────────── */}
      <section className="border-t border-zinc-200 bg-zinc-50 py-16">
        <div className="mx-auto max-w-2xl px-4 text-center sm:px-6">
          <h2 className="mb-4 text-2xl font-bold tracking-tight text-zinc-900">
            Start in minutes. Ship with data.
          </h2>
          <p className="mb-2 text-zinc-500">
            Free tier: 5 runs/month, up to 50 VUs, 5 minutes each.
          </p>
          <p className="mb-6 text-sm text-zinc-400">No card needed.</p>
          <Link
            href="/signup"
            className="inline-flex h-10 items-center rounded-md bg-primary px-8 text-sm font-medium text-white transition-colors hover:bg-indigo-800"
          >
            Create free account
          </Link>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────────────── */}
      <footer className="border-t border-zinc-200 bg-white py-12">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
            <div>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                Product
              </p>
              <ul className="space-y-2 text-sm text-zinc-500">
                <li>
                  <Link href="/pricing" className="hover:text-zinc-900 transition-colors">
                    Pricing
                  </Link>
                </li>
                <li>
                  <Link href="/changelog" className="hover:text-zinc-900 transition-colors">
                    Changelog
                  </Link>
                </li>
                <li>
                  <Link href="/status" className="hover:text-zinc-900 transition-colors">
                    Status
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                Docs
              </p>
              <ul className="space-y-2 text-sm text-zinc-500">
                <li>
                  <Link href="/docs" className="hover:text-zinc-900 transition-colors">
                    Quickstart
                  </Link>
                </li>
                <li>
                  <Link href="/docs/k6-script-reference" className="hover:text-zinc-900 transition-colors">
                    k6 Reference
                  </Link>
                </li>
                <li>
                  <Link href="/docs/api-auth" className="hover:text-zinc-900 transition-colors">
                    API Auth
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                Blog
              </p>
              <ul className="space-y-2 text-sm text-zinc-500">
                <li>
                  <Link href="/blog/why-testlyn" className="hover:text-zinc-900 transition-colors">
                    Why Testlyn
                  </Link>
                </li>
                <li>
                  <Link href="/blog/agpl-safe-k6" className="hover:text-zinc-900 transition-colors">
                    AGPL-safe k6
                  </Link>
                </li>
                <li>
                  <Link href="/blog/bigquery-streaming-for-load-tests" className="hover:text-zinc-900 transition-colors">
                    BigQuery metrics
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                Company
              </p>
              <ul className="space-y-2 text-sm text-zinc-500">
                <li>
                  <a
                    href="mailto:hello@example.com"
                    className="hover:text-zinc-900 transition-colors"
                  >
                    Contact
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div className="mt-10 border-t border-zinc-100 pt-6 text-center text-xs text-zinc-400">
            &copy; {new Date().getFullYear()} Testlyn. Built by engineers, for engineers.
          </div>
        </div>
      </footer>
    </>
  );
}
