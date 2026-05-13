import type { Metadata } from "next";

export const metadata: Metadata = { title: "Docs" };

export default function DocsPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-20 sm:px-6">
      <h1 className="mb-4 text-3xl font-bold tracking-tight text-zinc-900">
        Documentation
      </h1>
      <p className="mb-8 text-zinc-500">
        Full documentation is coming soon. In the meantime, here are the
        essentials to get started.
      </p>

      <div className="space-y-8">
        <section aria-labelledby="quickstart-heading">
          <h2
            id="quickstart-heading"
            className="mb-3 text-lg font-semibold text-zinc-900"
          >
            Quickstart
          </h2>
          <ol className="list-decimal space-y-2 pl-5 text-sm leading-relaxed text-zinc-600">
            <li>Sign up and create an organization.</li>
            <li>Create a project, then a test with a k6 script.</li>
            <li>Hit &ldquo;Run&rdquo; — live metrics appear within 5 seconds.</li>
            <li>
              Download the PDF report or query raw data from BigQuery via the
              API.
            </li>
          </ol>
        </section>

        <section aria-labelledby="api-heading">
          <h2
            id="api-heading"
            className="mb-3 text-lg font-semibold text-zinc-900"
          >
            REST API
          </h2>
          <p className="text-sm text-zinc-500">
            All UI actions are available via API. Authenticate with your IdP JWT
            or an API key.
          </p>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-zinc-900 p-4 text-xs text-zinc-300 font-mono">
            {`POST /v1/tests/:id/runs
Authorization: Bearer <your-api-key>

# Starts a run and returns run metadata.`}
          </pre>
        </section>

        <section aria-labelledby="script-heading">
          <h2
            id="script-heading"
            className="mb-3 text-lg font-semibold text-zinc-900"
          >
            Writing k6 scripts
          </h2>
          <p className="text-sm text-zinc-500">
            Testlyn runs stock{" "}
            <code className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-xs text-zinc-800">
              grafana/k6
            </code>{" "}
            — any valid k6 script works here. No proprietary extensions
            required.
          </p>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-zinc-900 p-4 text-xs text-zinc-300 font-mono">
            {`import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  vus: 50,
  duration: '2m',
};

export default function () {
  http.get('https://your-api.example.com/health');
  sleep(1);
}`}
          </pre>
        </section>
      </div>
    </div>
  );
}
