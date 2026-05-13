"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MonacoEditor } from "@/components/editor/monaco-editor";
import type { CreateTestRequest } from "@testlyn/shared";

const DEFAULT_SCRIPT = `import http from "k6/http";
import { sleep, check } from "k6";

export const options = {
  vus: __VUS__,
  duration: "__DURATION__s",
};

export default function () {
  const res = http.get("https://your-api.example.com/health");

  check(res, {
    "status is 200": (r) => r.status === 200,
    "response time < 500ms": (r) => r.timings.duration < 500,
  });

  sleep(1);
}
`;

export default function NewTestPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project") ?? "";

  const [name, setName] = useState("");
  const [vus, setVus] = useState(10);
  const [duration, setDuration] = useState(30);
  const [script, setScript] = useState(
    DEFAULT_SCRIPT.replace("__VUS__", "10").replace("__DURATION__", "30")
  );
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: CreateTestRequest) =>
      api.projects.createTest(projectId, payload),
    onSuccess: () => {
      router.push(`/projects/${projectId}`);
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Failed to create test");
    },
  });

  function handleVusChange(value: number) {
    setVus(value);
    setScript((s) =>
      s.replace(/vus: \d+/, `vus: ${value}`)
    );
  }

  function handleDurationChange(value: number) {
    setDuration(value);
    setScript((s) =>
      s.replace(/duration: "\d+s"/, `duration: "${value}s"`)
    );
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!projectId) {
      setError("No project selected.");
      return;
    }
    mutation.mutate({
      name,
      product: "load",
      config: {
        script,
        vus,
        duration,
        thresholds: {},
      },
    });
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-8">
        <button
          onClick={() => router.back()}
          className="mb-4 flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-100"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
          Back
        </button>
        <h1 className="text-2xl font-bold tracking-tight text-zinc-100">New test</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Configure your k6 load test. The script editor gives you full control.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {error && (
          <div role="alert" className="rounded-md bg-alert/10 px-3 py-2 text-sm text-alert">
            {error}
          </div>
        )}

        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <label htmlFor="test-name" className="mb-1 block text-sm font-medium text-zinc-300">
            Test name
          </label>
          <Input
            id="test-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Homepage load test"
            className="border-zinc-700 bg-zinc-800 text-zinc-100 placeholder:text-zinc-500"
          />
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <h2 className="mb-4 text-sm font-medium text-zinc-300">Load parameters</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="vus" className="mb-1 block text-sm text-zinc-400">
                Virtual users (VUs)
              </label>
              <Input
                id="vus"
                type="number"
                min={1}
                max={10000}
                required
                value={vus}
                onChange={(e) => handleVusChange(Number(e.target.value))}
                className="border-zinc-700 bg-zinc-800 text-zinc-100"
              />
            </div>
            <div>
              <label htmlFor="duration" className="mb-1 block text-sm text-zinc-400">
                Duration (seconds)
              </label>
              <Input
                id="duration"
                type="number"
                min={1}
                max={86400}
                required
                value={duration}
                onChange={(e) => handleDurationChange(Number(e.target.value))}
                className="border-zinc-700 bg-zinc-800 text-zinc-100"
              />
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          <h2 className="mb-3 text-sm font-medium text-zinc-300">
            k6 script
            <span className="ml-2 font-mono text-xs text-zinc-500">JavaScript</span>
          </h2>
          <div className="overflow-hidden rounded-lg border border-zinc-700">
            <MonacoEditor
              value={script}
              onChange={(v) => setScript(v ?? "")}
              language="javascript"
              height="380px"
            />
          </div>
          <p className="mt-2 text-xs text-zinc-500">
            Full k6 scripting API available. See{" "}
            <a
              href="https://grafana.com/docs/k6/latest/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              k6 docs
            </a>{" "}
            for reference.
          </p>
        </div>

        <div className="flex justify-end gap-3">
          <Button
            type="button"
            variant="ghost"
            onClick={() => router.back()}
            className="text-zinc-400 hover:text-zinc-100"
          >
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending || !name.trim() || !projectId}>
            {mutation.isPending ? "Creating…" : "Create test"}
          </Button>
        </div>
      </form>
    </div>
  );
}
