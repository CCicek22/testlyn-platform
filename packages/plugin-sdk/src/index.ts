/**
 * @testlyn/plugin-sdk
 *
 * Define runners, integrations, and panels for the Testlyn marketplace.
 * All plugin code executes inside a Node.js worker_thread sandbox — the host
 * process never imports plugin code directly. See README.md for security model.
 */

// ---------------------------------------------------------------------------
// Shared primitive types
// ---------------------------------------------------------------------------

/** ISO-8601 timestamp string */
export type ISOTimestamp = string;

/** Arbitrary key/value metadata attached to a test run */
export type RunMetadata = Record<string, string | number | boolean>;

// ---------------------------------------------------------------------------
// Lifecycle hook payloads
// ---------------------------------------------------------------------------

export interface TestStartPayload {
  runId: string;
  testId: string;
  orgId: string;
  product: string;
  config: Record<string, unknown>;
  startedAt: ISOTimestamp;
}

export interface TestCompletePayload {
  runId: string;
  testId: string;
  orgId: string;
  product: string;
  status: "passed" | "failed" | "aborted";
  durationMs: number;
  completedAt: ISOTimestamp;
  summary: Record<string, unknown>;
}

export interface MetricPayload {
  runId: string;
  name: string;
  value: number;
  unit: string;
  tags: Record<string, string>;
  timestamp: ISOTimestamp;
}

export interface RenderPayload {
  runId: string;
  /** Aggregated metrics for the run */
  metrics: MetricPayload[];
  /** Arbitrary run metadata */
  meta: RunMetadata;
}

// ---------------------------------------------------------------------------
// Lifecycle hooks
// ---------------------------------------------------------------------------

export interface LifecycleHooks {
  /** Called immediately after the test run is created and queued. */
  onTestStart?: (payload: TestStartPayload) => void | Promise<void>;

  /** Called after the runner process exits and the final summary is written. */
  onTestComplete?: (payload: TestCompletePayload) => void | Promise<void>;

  /** Called for each streaming metric event during an active run. */
  onMetric?: (payload: MetricPayload) => void | Promise<void>;

  /**
   * Called when the dashboard renders this plugin's panel.
   * Return an object that the React panel component receives as props.
   */
  onRender?: (payload: RenderPayload) => Record<string, unknown> | Promise<Record<string, unknown>>;
}

// ---------------------------------------------------------------------------
// Runner plugin
// ---------------------------------------------------------------------------

export interface RunnerCapabilities {
  /** Products this runner supports, e.g. ["load", "functional"] */
  products: string[];
  /** Human-readable list of what the runner can do */
  features: string[];
}

export interface RunnerDefinition {
  /** Unique slug, e.g. "k6-extended" */
  slug: string;
  name: string;
  description: string;
  version: string;
  capabilities: RunnerCapabilities;
  hooks: LifecycleHooks;
  /**
   * Execute the test. The host calls this inside a worker_thread.
   * Resolve with exit code (0 = success).
   */
  execute: (context: RunnerExecuteContext) => Promise<number>;
}

export interface RunnerExecuteContext {
  runId: string;
  testId: string;
  scriptUri: string;
  config: Record<string, unknown>;
  /** Write a single metric row (forwarded to BQ sidecar via stdout). */
  emitMetric: (metric: Omit<MetricPayload, "runId">) => void;
}

/**
 * Define a runner plugin.
 *
 * @example
 * ```ts
 * import { defineRunner } from "@testlyn/plugin-sdk";
 *
 * export default defineRunner({
 *   slug: "my-runner",
 *   name: "My Custom Runner",
 *   description: "Runs tests using my-framework",
 *   version: "0.1.0",
 *   capabilities: { products: ["load"], features: ["http2", "grpc"] },
 *   hooks: {
 *     onTestStart: ({ runId }) => console.log("Starting", runId),
 *   },
 *   execute: async (ctx) => {
 *     // ... invoke framework, emit metrics
 *     return 0;
 *   },
 * });
 * ```
 */
export function defineRunner(definition: RunnerDefinition): RunnerDefinition {
  return definition;
}

// ---------------------------------------------------------------------------
// Integration plugin
// ---------------------------------------------------------------------------

export interface IntegrationTrigger {
  /** Lifecycle event that fires this integration */
  on: keyof LifecycleHooks;
}

export interface IntegrationDefinition {
  slug: string;
  name: string;
  description: string;
  version: string;
  /** Config schema as JSON Schema object (used to render settings UI) */
  configSchema: Record<string, unknown>;
  triggers: IntegrationTrigger[];
  hooks: LifecycleHooks;
}

/**
 * Define an integration plugin (e.g. Slack notifier, PagerDuty, Datadog forwarder).
 *
 * @example
 * ```ts
 * import { defineIntegration } from "@testlyn/plugin-sdk";
 *
 * export default defineIntegration({
 *   slug: "slack-notifier",
 *   name: "Slack Notifier",
 *   description: "Posts run results to a Slack channel",
 *   version: "0.1.0",
 *   configSchema: {
 *     type: "object",
 *     properties: { webhookUrl: { type: "string", format: "uri" } },
 *     required: ["webhookUrl"],
 *   },
 *   triggers: [{ on: "onTestComplete" }],
 *   hooks: {
 *     onTestComplete: async ({ runId, status }) => {
 *       // ... post to Slack
 *     },
 *   },
 * });
 * ```
 */
export function defineIntegration(definition: IntegrationDefinition): IntegrationDefinition {
  return definition;
}

// ---------------------------------------------------------------------------
// Panel plugin
// ---------------------------------------------------------------------------

export interface PanelDefinition {
  slug: string;
  name: string;
  description: string;
  version: string;
  /** Products this panel applies to */
  products: string[];
  /**
   * React component source path (resolved relative to plugin root).
   * Must be a default export of a React functional component.
   * The host sandboxes rendering via a micro-frontend iframe.
   */
  componentPath: string;
  hooks: Pick<LifecycleHooks, "onRender">;
}

/**
 * Define a dashboard panel plugin.
 *
 * @example
 * ```ts
 * import { definePanel } from "@testlyn/plugin-sdk";
 *
 * export default definePanel({
 *   slug: "p95-heatmap",
 *   name: "P95 Latency Heatmap",
 *   description: "Heatmap of p95 latency over the run timeline",
 *   version: "0.1.0",
 *   products: ["load"],
 *   componentPath: "./P95HeatmapPanel.tsx",
 *   hooks: {
 *     onRender: async ({ metrics }) => ({ data: metrics }),
 *   },
 * });
 * ```
 */
export function definePanel(definition: PanelDefinition): PanelDefinition {
  return definition;
}

// ---------------------------------------------------------------------------
// Plugin manifest (union type for marketplace registry)
// ---------------------------------------------------------------------------

export type PluginDefinition = RunnerDefinition | IntegrationDefinition | PanelDefinition;

export type PluginKind = "runner" | "integration" | "panel";

export function pluginKind(plugin: PluginDefinition): PluginKind {
  if ("execute" in plugin) return "runner";
  if ("configSchema" in plugin) return "integration";
  return "panel";
}
