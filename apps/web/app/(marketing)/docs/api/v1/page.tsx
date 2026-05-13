/**
 * Public API reference page — /docs/api/v1
 *
 * Loads openapi-v1.yaml from the repo (server-side at build time) and renders
 * it via @scalar/api-reference-react with Testlyn's dark/indigo theme.
 *
 * The component is a React Server Component — no "use client" needed.
 */
import type { Metadata } from "next";
import fs from "node:fs";
import path from "node:path";
import { ApiReferenceReact } from "@scalar/api-reference-react";

export const metadata: Metadata = {
  title: "API Reference v1 — Testlyn",
  description: "Full OpenAPI v1 reference for the Testlyn public API.",
};

// At build time, read the YAML from the repo root so the Next.js bundle
// includes it as a static string (no runtime GCS/network dependency).
function loadOpenApiSpec(): string {
  // Works from both local dev (repo root) and Cloud Build (WORKDIR = repo root)
  const candidate = path.resolve(process.cwd(), "../../docs/api/openapi-v1.yaml");
  if (fs.existsSync(candidate)) {
    return fs.readFileSync(candidate, "utf-8");
  }
  // Fallback: relative to apps/web when running `next dev` from apps/web
  const fallback = path.resolve(process.cwd(), "docs/api/openapi-v1.yaml");
  if (fs.existsSync(fallback)) {
    return fs.readFileSync(fallback, "utf-8");
  }
  return "";
}

const RATE_LIMIT_NOTE = `
**Rate limits** are enforced per API key per minute:

| Plan | Requests / min |
|------|---------------|
| Free | 60 |
| Hobby | 600 |
| Pro | 6,000 |
| Business | 60,000 |

All responses include \`X-RateLimit-Limit\` and \`X-RateLimit-Remaining\` headers.
Exceeded limits return HTTP \`429\` with a \`Retry-After\` header (60 s).

**Authentication:** pass your API key via the \`X-Api-Key\` header, or a Firebase
ID token via \`Authorization: Bearer <token>\`.
`.trim();

export default function ApiV1ReferencePage() {
  const spec = loadOpenApiSpec();

  return (
    <div className="min-h-screen bg-[#0A0A0B]">
      {/* Page header */}
      <div className="border-b border-zinc-800 bg-[#0A0A0B] px-6 py-8">
        <div className="mx-auto max-w-6xl">
          <div className="flex items-center gap-3">
            <span className="rounded bg-[#3730A3]/20 px-2 py-0.5 font-mono text-xs text-[#3730A3] ring-1 ring-[#3730A3]/30">
              v1
            </span>
            <h1 className="text-xl font-semibold text-white">API Reference</h1>
          </div>
          <p className="mt-1 text-sm text-zinc-400">
            OpenAPI 3.1 — generated from the live FastAPI schema.
          </p>

          {/* Rate limit notice */}
          <details className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3 text-sm text-zinc-300">
            <summary className="cursor-pointer font-medium text-zinc-200 hover:text-white">
              Rate limits &amp; authentication
            </summary>
            <div className="mt-3 space-y-2 whitespace-pre-wrap font-mono text-xs text-zinc-400">
              {RATE_LIMIT_NOTE}
            </div>
          </details>
        </div>
      </div>

      {/* Scalar API Reference embed */}
      {spec ? (
        <ApiReferenceReact
          configuration={{
            spec: { content: spec },
            theme: "none",
            darkMode: true,
            layout: "sidebar",
            hideModels: false,
            hideDownloadButton: false,
            defaultOpenAllTags: false,
            customCss: `
              :root {
                --scalar-color-1: #ffffff;
                --scalar-color-2: #a1a1aa;
                --scalar-color-3: #71717a;
                --scalar-background-1: #0a0a0b;
                --scalar-background-2: #111113;
                --scalar-background-3: #18181b;
                --scalar-border-color: #27272a;
                --scalar-color-accent: #3730a3;
                --scalar-sidebar-background-1: #0a0a0b;
                --scalar-sidebar-color-1: #ffffff;
                --scalar-sidebar-color-2: #a1a1aa;
                --scalar-sidebar-border-color: #27272a;
              }
            `,
          }}
        />
      ) : (
        <div className="flex min-h-[40vh] items-center justify-center text-zinc-500">
          <p className="text-sm">
            OpenAPI spec not found. Run{" "}
            <code className="rounded bg-zinc-800 px-1 py-0.5 font-mono text-xs">
              python scripts/export-openapi.py
            </code>{" "}
            from the repo root.
          </p>
        </div>
      )}
    </div>
  );
}
