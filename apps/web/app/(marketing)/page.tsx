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
      <section className="relative overflow-hidden px-4 pb-16 pt-16 sm:px-6 sm:pt-24">
        <div className="absolute inset-0 -z-10 test-grid opacity-60" aria-hidden="true" />
        <div className="absolute left-1/2 top-24 -z-10 h-72 w-72 -translate-x-1/2 rounded-full bg-primary/20 blur-3xl" aria-hidden="true" />
        <div className="mx-auto max-w-6xl">
        <div className="reveal-on-scroll mb-5 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 font-mono text-xs font-medium text-primary backdrop-blur-xl">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
          QA SIGNAL ONLINE / LOAD TESTING
        </div>

        <h1 className="reveal-on-scroll mb-4 max-w-4xl font-display text-4xl font-bold tracking-tight text-[var(--glass-ink)] sm:text-5xl lg:text-7xl">
          Testlyn turns release risk into{" "}
          <span className="text-primary">observable signal.</span>
        </h1>

        <p className="reveal-on-scroll mb-8 max-w-2xl text-lg leading-relaxed text-[var(--glass-muted)]">
          Run k6 with native BigQuery streaming, live charts, and AI bottleneck
          explanations — without the AGPL surface.
        </p>

        <div className="reveal-on-scroll flex flex-wrap gap-3">
          <Link
            href="/signup"
            className="trace-glow inline-flex h-10 items-center rounded-md bg-primary px-6 text-sm font-semibold text-[#031111] transition-all hover:-translate-y-0.5 hover:bg-primary-100"
          >
            Start free — no card required
          </Link>
          <Link
            href="/docs"
            className="inline-flex h-10 items-center rounded-md border border-zinc-300 bg-[var(--glass-panel)] px-6 text-sm font-medium text-[var(--glass-muted)] backdrop-blur-xl transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:bg-primary/10"
          >
            Read the docs
          </Link>
        </div>

        {/* Hero chart — static SVG, no client-only JS gating LCP */}
        <div className="reveal-on-scroll mt-14">
          <HeroChart />
        </div>
        </div>
      </section>

      {/* ── How it works ──────────────────────────────────────── */}
      <section className="reveal-on-scroll border-t border-[var(--glass-border)] bg-[var(--glass-panel)] py-20 backdrop-blur-xl">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <h2 className="mb-3 text-2xl font-bold tracking-tight text-[var(--glass-ink)] sm:text-3xl">
            How it works
          </h2>
          <p className="mb-12 text-[var(--glass-muted)]">Three steps. No black boxes.</p>

          <div className="grid grid-cols-1 gap-10 lg:grid-cols-3">
            {HOW_IT_WORKS.map((item) => (
              <article key={item.step} className="liquid-glass flex flex-col gap-4 rounded-xl p-5 transition-all duration-300">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs font-semibold text-primary">
                    {item.step}
                  </span>
                  <h3 className="font-semibold text-[var(--glass-ink)]">{item.title}</h3>
                </div>
                <p className="text-sm leading-relaxed text-[var(--glass-muted)]">
                  {item.description}
                </p>
                <pre className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/80 p-4 text-xs leading-relaxed text-zinc-300 shadow-inner">
                  <code className="font-mono">{item.code}</code>
                </pre>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ── Why Testlyn ───────────────────────────────────────── */}
      <section className="reveal-on-scroll mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <h2 className="mb-3 text-2xl font-bold tracking-tight text-[var(--glass-ink)] sm:text-3xl">
          Why Testlyn
        </h2>
        <p className="mb-12 text-[var(--glass-muted)]">
          No fluff. Here is what you actually get.
        </p>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {WHY_CARDS.map((card) => (
            <article
              key={card.title}
              className={`liquid-glass flex flex-col gap-3 rounded-xl ${card.accent} p-6 transition-all duration-300`}
            >
              <span className="inline-block rounded-full border border-[var(--glass-border)] bg-[var(--glass-panel-strong)] px-2 py-0.5 font-mono text-xs font-medium text-[var(--glass-muted)]">
                {card.label}
              </span>
              <h3 className="font-semibold text-[var(--glass-ink)]">{card.title}</h3>
              <p className="text-sm leading-relaxed text-[var(--glass-muted)]">{card.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ── Mobile app preview ───────────────────────────────── */}
      <section className="reveal-on-scroll border-t border-[var(--glass-border)] bg-[var(--glass-panel)] py-20 backdrop-blur-xl">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-[1fr_0.85fr]">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 font-mono text-xs font-medium text-primary backdrop-blur-xl">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" aria-hidden="true" />
              MOBILE APP IN THE WORKS
            </div>
            <h2 className="mb-4 max-w-2xl text-3xl font-bold tracking-tight text-[var(--glass-ink)] sm:text-4xl">
              Carry run signal from deploy review to incident call.
            </h2>
            <p className="mb-8 max-w-xl text-base leading-relaxed text-[var(--glass-muted)]">
              A companion app is planned for live run alerts, threshold status,
              and quick handoff notes. This is a preview placeholder while we
              build the real mobile experience.
            </p>

            <div className="flex flex-wrap gap-3" aria-label="Mobile app download badges coming soon">
              <a
                href="#"
                aria-disabled="true"
                className="liquid-glass inline-flex min-w-40 cursor-not-allowed items-center gap-3 rounded-xl px-4 py-3 opacity-75 transition-all"
              >
                <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 font-mono text-xs text-primary">
                  iOS
                </span>
                <span>
                  <span className="block font-mono text-[10px] uppercase tracking-wide text-[var(--glass-muted)]">
                    Coming soon on
                  </span>
                  <span className="block text-sm font-semibold text-[var(--glass-ink)]">
                    App Store
                  </span>
                </span>
              </a>
              <a
                href="#"
                aria-disabled="true"
                className="liquid-glass inline-flex min-w-40 cursor-not-allowed items-center gap-3 rounded-xl px-4 py-3 opacity-75 transition-all"
              >
                <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-success/25 bg-success/10 font-mono text-xs text-success">
                  GP
                </span>
                <span>
                  <span className="block font-mono text-[10px] uppercase tracking-wide text-[var(--glass-muted)]">
                    Coming soon on
                  </span>
                  <span className="block text-sm font-semibold text-[var(--glass-ink)]">
                    Google Play
                  </span>
                </span>
              </a>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-sm">
            <div className="absolute -left-8 top-10 h-32 w-32 rounded-full bg-primary/20 blur-3xl" aria-hidden="true" />
            <div className="absolute -right-6 bottom-12 h-28 w-28 rounded-full bg-alert/20 blur-3xl" aria-hidden="true" />
            <div className="liquid-glass relative mx-auto rounded-[2.25rem] p-3 shadow-2xl">
              <div className="rounded-[1.8rem] border border-zinc-800 bg-zinc-950 p-3">
                <div className="mx-auto mb-3 h-1.5 w-16 rounded-full bg-zinc-800" aria-hidden="true" />
                <div className="test-grid overflow-hidden rounded-[1.35rem] border border-zinc-800 bg-[#05090B] p-4 text-zinc-100">
                  <div className="mb-5 flex items-center justify-between">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-wide text-primary">
                        testlyn mobile
                      </p>
                      <p className="mt-1 text-lg font-semibold">Run watch</p>
                    </div>
                    <span className="rounded-full border border-success/30 bg-success/10 px-2 py-1 font-mono text-[10px] text-success">
                      pass
                    </span>
                  </div>

                  <div className="space-y-3">
                    <div className="rounded-2xl border border-primary/20 bg-primary/10 p-3">
                      <div className="mb-2 flex items-center justify-between font-mono text-[10px] text-zinc-400">
                        <span>production-stress-v3</span>
                        <span>500 VUs</span>
                      </div>
                      <div className="flex items-end gap-2">
                        <span className="font-mono text-3xl font-semibold text-primary">112</span>
                        <span className="pb-1 text-xs text-zinc-400">ms p95</span>
                      </div>
                      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-zinc-800">
                        <div className="h-full w-[72%] rounded-full bg-primary shadow-[0_0_24px_rgba(24,242,195,0.45)]" />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3">
                        <p className="font-mono text-[10px] uppercase text-zinc-500">errors</p>
                        <p className="mt-1 font-mono text-xl text-success">0.4%</p>
                      </div>
                      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3">
                        <p className="font-mono text-[10px] uppercase text-zinc-500">alert</p>
                        <p className="mt-1 font-mono text-xl text-warn">warm</p>
                      </div>
                    </div>

                    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/70 p-3">
                      <p className="mb-2 font-mono text-[10px] uppercase text-zinc-500">
                        handoff note
                      </p>
                      <p className="text-xs leading-relaxed text-zinc-300">
                        p95 is stable after ramp. Watch checkout pool if error
                        rate crosses 1%.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Bottom CTA ────────────────────────────────────────── */}
      <section className="reveal-on-scroll border-t border-[var(--glass-border)] bg-[var(--glass-panel)] py-16 backdrop-blur-xl">
        <div className="mx-auto max-w-2xl px-4 text-center sm:px-6">
          <h2 className="mb-4 text-2xl font-bold tracking-tight text-[var(--glass-ink)]">
            Start in minutes. Ship with data.
          </h2>
          <p className="mb-2 text-[var(--glass-muted)]">
            Free tier: 5 runs/month, up to 50 VUs, 5 minutes each.
          </p>
          <p className="mb-6 text-sm text-[var(--glass-faint)]">No card needed.</p>
          <Link
            href="/signup"
            className="trace-glow inline-flex h-10 items-center rounded-md bg-primary px-8 text-sm font-semibold text-[#031111] transition-all hover:-translate-y-0.5 hover:bg-primary-100"
          >
            Create free account
          </Link>
        </div>
      </section>

      {/* ── Footer ────────────────────────────────────────────── */}
      <footer className="border-t border-[var(--glass-border)] bg-[var(--glass-panel)] py-12 backdrop-blur-xl">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
            <div>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--glass-faint)]">
                Product
              </p>
              <ul className="space-y-2 text-sm text-[var(--glass-muted)]">
                <li>
                  <Link href="/pricing" className="hover:text-[var(--glass-ink)] transition-colors">
                    Pricing
                  </Link>
                </li>
                <li>
                  <Link href="/changelog" className="hover:text-[var(--glass-ink)] transition-colors">
                    Changelog
                  </Link>
                </li>
                <li>
                  <Link href="/status" className="hover:text-[var(--glass-ink)] transition-colors">
                    Status
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--glass-faint)]">
                Docs
              </p>
              <ul className="space-y-2 text-sm text-[var(--glass-muted)]">
                <li>
                  <Link href="/docs" className="hover:text-[var(--glass-ink)] transition-colors">
                    Quickstart
                  </Link>
                </li>
                <li>
                  <Link href="/docs/k6-script-reference" className="hover:text-[var(--glass-ink)] transition-colors">
                    k6 Reference
                  </Link>
                </li>
                <li>
                  <Link href="/docs/api-auth" className="hover:text-[var(--glass-ink)] transition-colors">
                    API Auth
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--glass-faint)]">
                Blog
              </p>
              <ul className="space-y-2 text-sm text-[var(--glass-muted)]">
                <li>
                  <Link href="/blog/why-testlyn" className="hover:text-[var(--glass-ink)] transition-colors">
                    Why Testlyn
                  </Link>
                </li>
                <li>
                  <Link href="/blog/agpl-safe-k6" className="hover:text-[var(--glass-ink)] transition-colors">
                    AGPL-safe k6
                  </Link>
                </li>
                <li>
                  <Link href="/blog/bigquery-streaming-for-load-tests" className="hover:text-[var(--glass-ink)] transition-colors">
                    BigQuery metrics
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--glass-faint)]">
                Company
              </p>
              <ul className="space-y-2 text-sm text-[var(--glass-muted)]">
                <li>
                  <a
                    href="mailto:hello@example.com"
                    className="hover:text-[var(--glass-ink)] transition-colors"
                  >
                    Contact
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div className="mt-10 border-t border-[var(--glass-border)] pt-6 text-center text-xs text-[var(--glass-faint)]">
            &copy; {new Date().getFullYear()} Testlyn. Built by engineers, for engineers.
          </div>
        </div>
      </footer>
    </>
  );
}
