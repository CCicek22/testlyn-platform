/**
 * sample-runner — Example Testlyn runner plugin for marketplace seeding.
 *
 * This plugin wraps a hypothetical "my-framework" CLI.
 * It demonstrates the full lifecycle hook surface and execute contract.
 */
import { defineRunner } from "@testlyn/plugin-sdk";

export default defineRunner({
  slug: "sample-runner",
  name: "Sample Runner",
  description:
    "Demonstration runner plugin. Shows the full @testlyn/plugin-sdk API surface. " +
    "Use this as a starting point for custom runners.",
  version: "0.1.0",
  capabilities: {
    products: ["load"],
    features: ["http1.1", "http2", "custom-metrics"],
  },
  hooks: {
    onTestStart: ({ runId, config }) => {
      console.log(`[sample-runner] Starting run ${runId}`, config);
    },
    onTestComplete: ({ runId, status, durationMs }) => {
      console.log(`[sample-runner] Run ${runId} finished: ${status} in ${durationMs}ms`);
    },
    onMetric: ({ name, value, unit }) => {
      // Forward to external observability system if needed
      console.log(`[sample-runner] metric ${name}=${value}${unit}`);
    },
    onRender: async ({ metrics }) => ({
      // Return props for the panel component
      totalRequests: metrics.filter((m) => m.name === "http_reqs").length,
      p95ms: metrics.find((m) => m.name === "http_req_duration_p95")?.value ?? 0,
    }),
  },
  execute: async (ctx) => {
    // In a real plugin: spawn child_process, parse output, emit metrics.
    // The host runs this inside worker_threads — no IPC to main process.
    console.log(`[sample-runner] execute() called for run ${ctx.runId}`);
    console.log(`[sample-runner] Script URI: ${ctx.scriptUri}`);

    // Emit a sample metric
    ctx.emitMetric({
      name: "sample_metric",
      value: 42,
      unit: "ms",
      tags: { phase: "sample" },
      timestamp: new Date().toISOString(),
    });

    return 0; // exit code 0 = success
  },
});
