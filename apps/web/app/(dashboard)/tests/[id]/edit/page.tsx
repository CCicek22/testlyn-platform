"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MonacoEditor } from "@/components/editor/monaco-editor";
import { Skeleton } from "@/components/ui/skeleton";
import type { PatchTestRequest } from "@testlyn/shared";

export default function EditTestPage() {
  const params = useParams<{ id: string }>();
  const testId = params.id;
  const router = useRouter();
  const qc = useQueryClient();

  const { data: test, isLoading, error } = useQuery({
    queryKey: ["test", testId],
    queryFn: () => api.tests.get(testId),
    enabled: !!testId,
  });

  const [name, setName] = useState("");
  const [vus, setVus] = useState(10);
  const [duration, setDuration] = useState(30);
  const [script, setScript] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  // Populate form once test loads. We accept the cascading render here because
  // the alternative (mounting the form via `key={test.id}`) would remount Monaco
  // on every refetch, losing cursor/scroll state.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (test) {
      setName(test.name);
      setVus(test.config.vus);
      setDuration(test.config.duration);
      setScript(test.config.script);
    }
  }, [test]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const mutation = useMutation({
    mutationFn: (payload: PatchTestRequest) => api.tests.patch(testId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["test", testId] });
      router.back();
    },
    onError: (err) => {
      setFormError(err instanceof Error ? err.message : "Failed to save test");
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    mutation.mutate({
      name,
      config: {
        script,
        vus,
        duration,
        thresholds: test?.config.thresholds ?? {},
      },
    });
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <div role="alert" className="rounded-md bg-alert/10 px-4 py-3 text-sm text-alert">
          Failed to load test.
        </div>
      </div>
    );
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
        {isLoading ? (
          <Skeleton className="h-8 w-48 bg-zinc-800" />
        ) : (
          <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
            Edit: {test?.name}
          </h1>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-6">
          <Skeleton className="h-24 w-full rounded-xl bg-zinc-800" />
          <Skeleton className="h-24 w-full rounded-xl bg-zinc-800" />
          <Skeleton className="h-96 w-full rounded-xl bg-zinc-800" />
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-6">
          {formError && (
            <div role="alert" className="rounded-md bg-alert/10 px-3 py-2 text-sm text-alert">
              {formError}
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
              placeholder="My load test"
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
                  onChange={(e) => setVus(Number(e.target.value))}
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
                  onChange={(e) => setDuration(Number(e.target.value))}
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
            <Button type="submit" disabled={mutation.isPending || !name.trim()}>
              {mutation.isPending ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
