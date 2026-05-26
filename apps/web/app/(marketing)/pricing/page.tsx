import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Testlyn pricing: Free, Hobby $19/mo, Pro $99/mo, Business $299/mo, Enterprise. No enterprise-call gates.",
};

type Feature = {
  label: string;
  tooltip?: string;
  free: string | boolean;
  hobby: string | boolean;
  pro: string | boolean;
  business: string | boolean;
  enterprise: string | boolean;
};

const FEATURES: Feature[] = [
  {
    label: "Tests / month",
    // CLS note: tooltip positioning is static; no layout shift from async data
    tooltip:
      "Free tier is capped at 50 VUs and 5 min per run to prevent abuse on shared infrastructure. Upgrade to Hobby for more headroom.",
    free: "5",
    hobby: "50",
    pro: "Unlimited",
    business: "Unlimited",
    enterprise: "Unlimited",
  },
  {
    label: "VU cap",
    free: "50",
    hobby: "200",
    pro: "1,000",
    business: "5,000",
    enterprise: "Unlimited",
  },
  {
    label: "Max duration",
    free: "5 min",
    hobby: "30 min",
    pro: "2 hr",
    business: "Unlimited",
    enterprise: "Unlimited",
  },
  {
    label: "Metric retention",
    free: "7 days",
    hobby: "30 days",
    pro: "90 days",
    business: "1 year",
    enterprise: "Custom",
  },
  {
    label: "Scheduled runs",
    free: false,
    hobby: false,
    pro: false,
    business: true,
    enterprise: true,
  },
  {
    label: "Daily AI digest",
    free: false,
    hobby: false,
    pro: true,
    business: true,
    enterprise: true,
  },
  {
    label: "PDF reports",
    free: false,
    hobby: false,
    pro: true,
    business: true,
    enterprise: true,
  },
  {
    label: "API key auth",
    free: false,
    hobby: true,
    pro: true,
    business: true,
    enterprise: true,
  },
  {
    label: "Custom domains",
    free: false,
    hobby: false,
    pro: false,
    business: true,
    enterprise: true,
  },
  {
    label: "Audit log",
    free: false,
    hobby: false,
    pro: false,
    business: true,
    enterprise: true,
  },
  {
    label: "SSO",
    free: false,
    hobby: false,
    pro: false,
    business: false,
    enterprise: true,
  },
  {
    label: "Priority support",
    free: false,
    hobby: false,
    pro: true,
    business: true,
    enterprise: true,
  },
  {
    label: "SLA",
    free: false,
    hobby: false,
    pro: false,
    business: false,
    enterprise: true,
  },
];

type Tier = {
  key: keyof Omit<Feature, "label" | "tooltip">;
  name: string;
  price: string;
  period: string;
  highlight: boolean;
  cta: string;
  href: string;
  disabled: boolean;
};

const TIERS: Tier[] = [
  {
    key: "free",
    name: "Free",
    price: "$0",
    period: "forever",
    highlight: false,
    cta: "Get started",
    href: "/signup",
    disabled: false,
  },
  {
    key: "hobby",
    name: "Hobby",
    price: "$19",
    period: "/ month",
    highlight: false,
    cta: "Start Hobby",
    href: "/signup",
    disabled: true,
  },
  {
    key: "pro",
    name: "Pro",
    price: "$99",
    period: "/ month",
    highlight: true,
    cta: "Start Pro",
    href: "/signup",
    disabled: true,
  },
  {
    key: "business",
    name: "Business",
    price: "$299",
    period: "/ month",
    highlight: false,
    cta: "Start Business",
    href: "/signup",
    disabled: true,
  },
  {
    key: "enterprise",
    name: "Enterprise",
    price: "Contact us",
    period: "",
    highlight: false,
    cta: "Contact sales",
    href: "mailto:hello@example.com",
    disabled: false,
  },
];

function Cell({ value }: { value: string | boolean }) {
  if (typeof value === "boolean") {
    return value ? (
      <span className="text-success font-semibold" aria-label="Included">
        ✓
      </span>
    ) : (
      <span className="text-zinc-300" aria-label="Not included">
        —
      </span>
    );
  }
  return <span className="font-mono text-sm text-zinc-700">{value}</span>;
}

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
      {/* Header */}
      <div className="mb-12 text-center">
        <h1 className="mb-3 text-3xl font-bold tracking-tight text-zinc-900 sm:text-4xl">
          Simple, transparent pricing.
        </h1>
        <p className="text-zinc-500">
          Start free. Scale when you need it. No surprise bills, no enterprise-call
          gates.
        </p>
      </div>

      {/* Tier cards — top summary */}
      <div className="mb-12 grid grid-cols-1 gap-4 sm:grid-cols-5">
        {TIERS.map((tier) => (
          <div
            key={tier.name}
            className={`flex flex-col rounded-xl border p-5 ${
              tier.highlight
                ? "border-primary bg-primary/5 shadow-md"
                : "border-zinc-200 bg-white"
            }`}
          >
            {tier.highlight && (
              <span className="mb-2 inline-block self-start rounded-full bg-primary px-2 py-0.5 text-xs font-semibold text-[#031111]">
                Most popular
              </span>
            )}
            <h2 className="font-bold text-zinc-900">{tier.name}</h2>
            <div className="mt-1 flex items-baseline gap-1">
              <span className="font-mono text-xl font-bold text-zinc-900">
                {tier.price}
              </span>
              {tier.period && (
                <span className="text-xs text-zinc-500">{tier.period}</span>
              )}
            </div>
            <div className="mt-4">
              {tier.disabled ? (
                <button
                  disabled
                  aria-label={`${tier.cta} — coming soon`}
                  className="w-full cursor-not-allowed rounded-md border border-zinc-200 py-1.5 text-xs font-medium text-zinc-400"
                >
                  {tier.cta}
                  <span className="ml-1 rounded bg-zinc-100 px-1 py-0.5 text-[10px] text-zinc-500">
                    coming soon
                  </span>
                </button>
              ) : (
                <Link
                  href={tier.href}
                  className={`block w-full rounded-md py-1.5 text-center text-xs font-medium transition-colors ${
                    tier.highlight
                      ? "bg-primary text-[#031111] hover:bg-primary-100"
                      : "border border-zinc-300 text-zinc-700 hover:bg-zinc-50"
                  }`}
                >
                  {tier.cta}
                </Link>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Full feature matrix */}
      <div className="overflow-x-auto rounded-xl border border-zinc-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 bg-zinc-50">
              <th className="px-4 py-3 text-left font-semibold text-zinc-900">
                Feature
              </th>
              {TIERS.map((t) => (
                <th
                  key={t.name}
                  className={`px-4 py-3 text-center font-semibold ${
                    t.highlight ? "text-primary" : "text-zinc-900"
                  }`}
                >
                  {t.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {FEATURES.map((feature, i) => (
              <tr
                key={feature.label}
                className={`border-b border-zinc-100 ${i % 2 === 0 ? "bg-white" : "bg-zinc-50/50"}`}
              >
                <td className="px-4 py-3 text-zinc-700">
                  <span className="flex items-center gap-1.5">
                    {feature.label}
                    {feature.tooltip && (
                      <span
                        title={feature.tooltip}
                        className="cursor-help text-zinc-400 underline decoration-dotted"
                        aria-label={`Info: ${feature.tooltip}`}
                      >
                        ?
                      </span>
                    )}
                  </span>
                </td>
                {TIERS.map((t) => (
                  <td key={t.name} className="px-4 py-3 text-center">
                    <Cell value={feature[t.key]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-6 text-center text-xs text-zinc-400">
        Prices in USD. Annual billing available — 20% off. Stripe Checkout integration
        in progress; paid CTAs are disabled until live.
      </p>

      {/* Why these limits — answers the "Free row" tooltip in prose */}
      <div className="mt-12 rounded-xl border border-zinc-200 bg-zinc-50 p-6">
        <h2 className="mb-2 font-semibold text-zinc-900">
          Why is the Free tier capped at 50 VUs and 5 minutes?
        </h2>
        <p className="text-sm leading-relaxed text-zinc-500">
          Every test run spins up a dedicated GCP Cloud Run Job. Infrastructure costs
          scale with VU count and duration — a 500 VU, 30-minute run costs roughly
          10x more compute than a 50 VU, 5-minute run. The Free cap lets us offer
          genuine free-tier access without throttling or cold-starting shared
          infrastructure. If you need more headroom for evaluation, email us at{" "}
          <a
            href="mailto:hello@example.com"
            className="text-primary underline decoration-dotted"
          >
            hello@example.com
          </a>
          .
        </p>
      </div>
    </div>
  );
}
