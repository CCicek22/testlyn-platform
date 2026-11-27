# @testlyn/plugin-sdk

Build runners, integrations, and dashboard panels for the Testlyn marketplace.

## Install

```bash
npm install @testlyn/plugin-sdk
# or
pnpm add @testlyn/plugin-sdk
```

## API surface

### `defineRunner(opts): RunnerDefinition`

Define a custom test runner. The host invokes `execute()` inside a Node.js `worker_threads` sandbox.

```ts
import { defineRunner } from "@testlyn/plugin-sdk";

export default defineRunner({
  slug: "my-runner",
  name: "My Runner",
  description: "...",
  version: "0.1.0",
  capabilities: { products: ["load"], features: ["grpc"] },
  hooks: { onTestStart, onTestComplete, onMetric, onRender },
  execute: async (ctx) => {
    ctx.emitMetric({ name: "rps", value: 1000, unit: "req/s", tags: {}, timestamp: new Date().toISOString() });
    return 0;
  },
});
```

### `defineIntegration(opts): IntegrationDefinition`

Define a lifecycle integration (Slack, PagerDuty, Datadog forwarder, etc.).

```ts
import { defineIntegration } from "@testlyn/plugin-sdk";

export default defineIntegration({
  slug: "slack-notifier",
  name: "Slack Notifier",
  description: "Post run results to Slack",
  version: "0.1.0",
  configSchema: {
    type: "object",
    properties: { webhookUrl: { type: "string", format: "uri" } },
    required: ["webhookUrl"],
  },
  triggers: [{ on: "onTestComplete" }],
  hooks: {
    onTestComplete: async ({ runId, status }) => { /* ... */ },
  },
});
```

### `definePanel(opts): PanelDefinition`

Define a custom dashboard panel rendered as a micro-frontend iframe.

```ts
import { definePanel } from "@testlyn/plugin-sdk";

export default definePanel({
  slug: "p95-heatmap",
  name: "P95 Latency Heatmap",
  description: "...",
  version: "0.1.0",
  products: ["load"],
  componentPath: "./P95HeatmapPanel.tsx",
  hooks: {
    onRender: async ({ metrics }) => ({ data: metrics }),
  },
});
```

## Lifecycle hooks

| Hook | Fired when |
|------|-----------|
| `onTestStart` | Run created and queued |
| `onTestComplete` | Runner process exits, summary written |
| `onMetric` | Each streaming metric event during active run |
| `onRender` | Dashboard renders the plugin's panel |

## Sandboxed execution

All plugin code runs inside `worker_threads` — isolated from the host process.

- No access to host filesystem beyond the plugin directory.
- No network access by default (use `configSchema` to declare required endpoints).
- `emitMetric()` writes NDJSON to stdout; the host pipes it to the BQ sidecar.
- CPU and memory limits enforced by the host before spawning the worker.

## Examples

See `examples/sample-runner/` for a complete annotated plugin.

## Publishing to the marketplace

Submit a PR to `https://github.com/CCicek22/testlyn-platform` with your plugin under
`packages/plugins/<your-slug>/`. Include:

1. `package.json` with `"testlyn-plugin": true`
2. `index.ts` exporting a `defineRunner | defineIntegration | definePanel` default
3. `README.md` with usage + config schema docs
4. Tests under `__tests__/`

The marketplace team reviews for security (sandbox escape, license compliance) before listing.
