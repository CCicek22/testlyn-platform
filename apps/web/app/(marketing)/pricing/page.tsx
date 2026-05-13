import type { Metadata } from "next";

export const metadata: Metadata = { title: "Pricing" };

const TIERS = [
  {
    name: "Free",
    price: "$0",
    period: "forever",
    highlight: false,
    features: [
      "5 runs / month",
      "50 VUs max",
      "5 min max duration",
      "7-day metric retention",
      "Community support",
    ],
    cta: "Get started",
    href: "/signup",
    disabled: false,
  },
  {
    name: "Hobby",
    price: "$19",
    period: "/ month",
    highlight: false,
    features: [
      "50 runs / month",
      "200 VUs max",
      "30 min max duration",
      "30-day metric retention",
      "Email support",
    ],
    cta: "Start Hobby",
    href: "/signup",
    disabled: true, // TODO: Stripe Checkout not live
  },
  {
    name: "Pro",
    price: "$99",
    period: "/ month",
    highlight: true,
    features: [
      "Unlimited runs",
      "1,000 VUs max",
      "2 hr max duration",
      "90-day metric retention",
      "AI daily summary",
      "PDF reports",
      "Priority support",
    ],
    cta: "Start Pro",
    href: "/signup",
    disabled: true, // TODO: Stripe Checkout not live
  },
  {
    name: "Business",
    price: "$299",
    period: "/ month",
    highlight: false,
    features: [
      "Everything in Pro",
      "5,000 VUs max",
      "Scheduled tests",
      "API key auth",
      "1-year retention",
      "SSO (Phase 2)",
      "Audit log",
    ],
    cta: "Start Business",
    href: "/signup",
    disabled: true,
  },
  {
    name: "Enterprise",
    price: "Contact us",
    period: "",
    highlight: false,
    features: [
      "Unlimited VUs",
      "Custom retention",
      "On-prem option (Phase 3)",
      "Dedicated support",
      "SLA",
      "Custom integrations",
    ],
    cta: "Contact sales",
    href: "mailto:hello@example.com",
    disabled: false,
  },
] as const;

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
      <div className="mb-12 text-center">
        <h1 className="mb-3 text-3xl font-bold tracking-tight text-zinc-900 sm:text-4xl">
          Simple, usage-based pricing.
        </h1>
        <p className="text-zinc-500">
          Start free. Scale when you need it. No surprise bills.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-5">
        {TIERS.map((tier) => (
          <div
            key={tier.name}
            className={`flex flex-col rounded-xl border p-6 ${
              tier.highlight
                ? "border-primary bg-primary/5 shadow-lg"
                : "border-zinc-200 bg-white"
            }`}
          >
            {tier.highlight && (
              <span className="mb-3 inline-block self-start rounded-full bg-primary px-2 py-0.5 text-xs font-semibold text-white">
                Most popular
              </span>
            )}
            <h2 className="text-lg font-bold text-zinc-900">{tier.name}</h2>
            <div className="mt-1 flex items-baseline gap-1">
              <span className="font-mono text-2xl font-bold text-zinc-900">
                {tier.price}
              </span>
              {tier.period && (
                <span className="text-sm text-zinc-500">{tier.period}</span>
              )}
            </div>

            <ul className="mt-4 flex flex-col gap-2 text-sm text-zinc-600">
              {tier.features.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <span className="mt-0.5 text-success" aria-hidden="true">
                    ✓
                  </span>
                  {f}
                </li>
              ))}
            </ul>

            <div className="mt-auto pt-6">
              {tier.disabled ? (
                <button
                  disabled
                  aria-label={`${tier.cta} — coming soon`}
                  className="w-full cursor-not-allowed rounded-md border border-zinc-300 py-2 text-sm font-medium text-zinc-400"
                >
                  {tier.cta}
                  <span className="ml-2 text-xs">(coming soon)</span>
                </button>
              ) : (
                <a
                  href={tier.href}
                  className={`block w-full rounded-md py-2 text-center text-sm font-medium transition-colors ${
                    tier.highlight
                      ? "bg-primary text-white hover:bg-primary-600"
                      : "border border-zinc-300 text-zinc-700 hover:bg-zinc-50"
                  }`}
                >
                  {tier.cta}
                </a>
              )}
            </div>
          </div>
        ))}
      </div>

      <p className="mt-8 text-center text-xs text-zinc-400">
        Prices in USD. Annual billing available (20% discount). Stripe Checkout
        integration in progress — CTAs are disabled until live.
      </p>
    </div>
  );
}
