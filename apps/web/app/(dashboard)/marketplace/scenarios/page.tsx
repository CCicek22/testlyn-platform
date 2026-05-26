import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ScenarioTemplate {
  slug: string;
  name: string;
  description: string;
  product: string;
  author: string;
  priceCents: number;
  tags: string[];
}

// ---------------------------------------------------------------------------
// Static templates — seeded in migration 0012_marketplace.
// Production: fetch from GET /v1/marketplace/scenarios.
// Paid templates stubbed — Stripe Connect not wired yet.
// ---------------------------------------------------------------------------

const SCENARIOS: ScenarioTemplate[] = [
  {
    slug: "k6-ramp-spike",
    name: "Ramp + Spike",
    description:
      "Three-stage k6 script: linear ramp-up to target VUs, hold, then inject a 10× spike for 30 s. " +
      "Validates autoscaling headroom and error budget under burst traffic.",
    product: "load",
    author: "Testlyn",
    priceCents: 0,
    tags: ["k6", "spike", "autoscaling"],
  },
  {
    slug: "k6-soak-24h",
    name: "24-Hour Soak",
    description:
      "Steady-state load over 24 h at 20% of peak capacity. " +
      "Surfaces memory leaks, connection pool exhaustion, and log rotation issues.",
    product: "load",
    author: "Testlyn",
    priceCents: 0,
    tags: ["k6", "soak", "reliability"],
  },
  {
    slug: "k6-breakpoint",
    name: "Breakpoint Finder",
    description:
      "Incrementally increases VUs until error rate exceeds 1% or p99 latency crosses 2 s. " +
      "Records the exact VU count at first threshold breach.",
    product: "load",
    author: "Testlyn",
    priceCents: 0,
    tags: ["k6", "capacity", "breakpoint"],
  },
  {
    slug: "k6-grpc-load",
    name: "gRPC Service Load",
    description:
      "Load test for unary gRPC endpoints. Parameterised request payload from CSV fixtures. " +
      "Reports per-RPC p50/p95/p99 and error codes.",
    product: "load",
    author: "community",
    priceCents: 0,
    tags: ["k6", "grpc", "microservices"],
  },
  {
    slug: "k6-checkout-flow",
    name: "E-Commerce Checkout Flow",
    description:
      "Realistic user journey: browse catalogue → add to cart → checkout → payment stub. " +
      "Models think-time between steps. Paid template — Stripe Connect integration coming soon.",
    product: "load",
    author: "community",
    priceCents: 1900,
    tags: ["k6", "e-commerce", "user-journey"],
  },
  {
    slug: "k6-websocket-chat",
    name: "WebSocket Chat Stress",
    description:
      "Simulates concurrent WebSocket connections with randomised message cadence. " +
      "Measures server broadcast latency and connection stability. Paid template — coming soon.",
    product: "load",
    author: "community",
    priceCents: 1200,
    tags: ["k6", "websocket", "realtime"],
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function PriceBadge({ priceCents }: { priceCents: number }) {
  if (priceCents === 0) {
    return (
      <Badge variant="outline" className="text-[#5CFF93] border-[#5CFF93]/30 bg-[#5CFF93]/10">
        Free
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="text-[#FFD166] border-[#FFD166]/30 bg-[#FFD166]/10">
      ${(priceCents / 100).toFixed(2)}
    </Badge>
  );
}

function TagList({ tags }: { tags: string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((t) => (
        <span
          key={t}
          className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono"
        >
          {t}
        </span>
      ))}
    </div>
  );
}

function ScenarioCard({ scenario }: { scenario: ScenarioTemplate }) {
  const isPaid = scenario.priceCents > 0;

  return (
    <Card className="bg-card border-border flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base leading-snug">{scenario.name}</CardTitle>
          <PriceBadge priceCents={scenario.priceCents} />
        </div>
        <CardDescription className="text-xs text-muted-foreground">
          by {scenario.author} &middot; product: {scenario.product}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1 space-y-3">
        <p className="text-sm text-muted-foreground leading-relaxed">{scenario.description}</p>
        <TagList tags={scenario.tags} />
      </CardContent>
      <CardFooter>
        {isPaid ? (
          <Button size="sm" variant="outline" disabled className="w-full opacity-60">
            Coming soon
          </Button>
        ) : (
          <Button size="sm" className="w-full bg-[#18F2C3] text-[#031111] hover:bg-[#B9FFF0]">
            Use template
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ScenariosPage() {
  const free = SCENARIOS.filter((s) => s.priceCents === 0);
  const paid = SCENARIOS.filter((s) => s.priceCents > 0);

  return (
    <div className="p-6 space-y-8 max-w-6xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Scenario Templates</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Ready-made k6 scripts. Pick one, fill in your target URL, and run.
        </p>
      </div>

      {/* Free templates */}
      <section>
        <h2 className="text-lg font-semibold mb-4">Free</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {free.map((s) => (
            <ScenarioCard key={s.slug} scenario={s} />
          ))}
        </div>
      </section>

      {/* Divider */}
      <div className="border-t border-border" />

      {/* Paid templates (stubbed) */}
      <section>
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-lg font-semibold">Community Paid</h2>
          <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded">
            Stripe Connect coming soon
          </span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {paid.map((s) => (
            <ScenarioCard key={s.slug} scenario={s} />
          ))}
        </div>
      </section>
    </div>
  );
}
