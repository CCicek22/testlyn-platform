import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PluginKind = "runner" | "integration" | "panel";

interface PluginCard {
  slug: string;
  kind: PluginKind;
  name: string;
  description: string;
  author: string;
  version: string;
  installCount: number;
  builtin: boolean;
}

// ---------------------------------------------------------------------------
// Static built-in plugins — always present; no DB call needed for scaffold.
// Production: fetch from GET /v1/marketplace/plugins and merge.
// ---------------------------------------------------------------------------

const BUILTIN_PLUGINS: PluginCard[] = [
  {
    slug: "k6-runner",
    kind: "runner",
    name: "k6 Load Runner",
    description: "Stock Grafana k6 runner. HTTP/1.1, HTTP/2, WebSockets, gRPC out of the box.",
    author: "Testlyn",
    version: "0.57.0",
    installCount: 0,
    builtin: true,
  },
  {
    slug: "bq-sidecar",
    kind: "integration",
    name: "BigQuery Sidecar",
    description: "Streams k6 metrics to BigQuery in real-time. Required for live charts and AI summaries.",
    author: "Testlyn",
    version: "0.1.0",
    installCount: 0,
    builtin: true,
  },
  {
    slug: "pdf-report",
    kind: "panel",
    name: "PDF Report Panel",
    description: "Renders a signed PDF summary of each run. Includes AI-generated executive summary.",
    author: "Testlyn",
    version: "0.1.0",
    installCount: 0,
    builtin: true,
  },
];

// ---------------------------------------------------------------------------
// Community plugins — seeded via migration 0012_marketplace.
// ---------------------------------------------------------------------------

const COMMUNITY_PLUGINS: PluginCard[] = [
  {
    slug: "slack-notifier",
    kind: "integration",
    name: "Slack Notifier",
    description: "Posts run results and threshold breaches to a Slack channel via webhook.",
    author: "community",
    version: "0.1.0",
    installCount: 142,
    builtin: false,
  },
  {
    slug: "p95-heatmap",
    kind: "panel",
    name: "P95 Latency Heatmap",
    description: "Dashboard panel showing p95 latency distribution as a heatmap over the run timeline.",
    author: "community",
    version: "0.2.1",
    installCount: 87,
    builtin: false,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const KIND_BADGE_COLORS: Record<PluginKind, string> = {
  runner: "bg-[#3730A3]/20 text-[#3730A3] dark:text-indigo-300",
  integration: "bg-[#10B981]/20 text-[#10B981]",
  panel: "bg-[#F59E0B]/20 text-[#F59E0B]",
};

function KindBadge({ kind }: { kind: PluginKind }) {
  return (
    <Badge variant="outline" className={KIND_BADGE_COLORS[kind]}>
      {kind}
    </Badge>
  );
}

function PluginGrid({ plugins, title }: { plugins: PluginCard[]; title: string }) {
  return (
    <section>
      <h2 className="text-lg font-semibold mb-4 text-foreground">{title}</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {plugins.map((p) => (
          <Card key={p.slug} className="bg-card border-border">
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-base leading-snug">{p.name}</CardTitle>
                <KindBadge kind={p.kind} />
              </div>
              <CardDescription className="text-xs text-muted-foreground">
                by {p.author} &middot; v{p.version}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground leading-relaxed">{p.description}</p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {p.builtin ? (
                    <span className="text-[#10B981] font-medium">built-in</span>
                  ) : (
                    <>{p.installCount.toLocaleString()} installs</>
                  )}
                </span>
                {p.builtin ? (
                  <Button size="sm" variant="outline" disabled>
                    Included
                  </Button>
                ) : (
                  <Button size="sm" variant="outline">
                    Install
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function MarketplacePage() {
  return (
    <div className="p-6 space-y-8 max-w-6xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Marketplace</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Runners, integrations, and dashboard panels for your test workflows.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href="/marketplace/scenarios">Scenario Templates</Link>
          </Button>
          <Button size="sm" asChild>
            <a
              href="https://github.com/CCicek22/testlyn/blob/main/packages/plugin-sdk/README.md"
              target="_blank"
              rel="noopener noreferrer"
            >
              Build a plugin
            </a>
          </Button>
        </div>
      </div>

      {/* Built-in */}
      <PluginGrid plugins={BUILTIN_PLUGINS} title="Built-in" />

      {/* Divider */}
      <div className="border-t border-border" />

      {/* Community */}
      <PluginGrid plugins={COMMUNITY_PLUGINS} title="Community" />
    </div>
  );
}
