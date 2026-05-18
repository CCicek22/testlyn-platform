"use client";

import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { getProduct, isProduct, type Product } from "@/lib/products";
import { RunList } from "@/components/runs/run-list";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/components/auth/auth-provider";
import type { Test, TestRun } from "@testlyn/shared";

function ConfigRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2.5 last:border-0">
      <span className="text-sm text-zinc-400">{label}</span>
      <span className="font-mono text-sm text-zinc-100">{value}</span>
    </div>
  );
}

export default function TestDetailPage() {
  const params = useParams<{ id: string }>();
  const testId = params.id;
  const router = useRouter();
  const { user } = useAuth();

  const {
    data: test,
    isLoading: testLoading,
    error: testError,
  } = useQuery<Test>({
    queryKey: ["test", testId],
    queryFn: () => api.tests.get(testId),
    enabled: !!testId && !!user,
  });

  // product is on the Test entity; fall back to "load" for the runs query key
  const product: Product =
    test?.product && isProduct(test.product) ? (test.product as Product) : "load";

  const {
    data: allRuns,
    isLoading: runsLoading,
    error: runsError,
  } = useQuery<TestRun[]>({
    queryKey: ["runs", product],
    queryFn: () => api.runs.list(product, 50),
    enabled: !!test && !!user,
  });

  // Filter to runs for this test (API doesn't support test_id filter yet)
  const runs: TestRun[] = allRuns?.filter((r) => r.test_id === testId) ?? [];

  const startRunMutation = useMutation({
    mutationFn: () => api.tests.startRun(testId),
    onSuccess: (run: TestRun) => {
      router.push(`/runs/${run.id}/${run.product}`);
    },
  });

  if (testError) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <div
          role="alert"
          className="rounded-md bg-alert/10 px-4 py-3 text-sm text-alert"
        >
          Failed to load test.
        </div>
      </div>
    );
  }

  const meta = getProduct(product);

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      {/* Back */}
      <button
        onClick={() => router.back()}
        className="mb-6 flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-100"
      >
        <svg
          className="h-4 w-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <path d="M19 12H5M12 5l-7 7 7 7" />
        </svg>
        Back
      </button>

      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          {testLoading ? (
            <Skeleton className="h-8 w-56 bg-zinc-800" />
          ) : (
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
                {test?.name}
              </h1>
              <Badge
                className="border-zinc-700 bg-zinc-800 font-mono text-xs text-zinc-400"
              >
                {testId.slice(0, 8)}
              </Badge>
              {test && (
                <span
                  className="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                  style={{
                    backgroundColor: `${meta.accent}22`,
                    color: meta.accent,
                  }}
                >
                  {meta.label}
                </span>
              )}
            </div>
          )}
          {test && (
            <p className="mt-1 text-sm text-zinc-500">
              Created {new Date(test.created_at).toLocaleDateString()}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Link href={`/tests/${testId}/edit`}>
            <Button
              variant="outline"
              size="sm"
              className="border-zinc-700 text-zinc-300 hover:text-zinc-100"
            >
              Edit
            </Button>
          </Link>
          <Button
            size="sm"
            onClick={() => startRunMutation.mutate()}
            disabled={startRunMutation.isPending || testLoading || !test}
            aria-label="Start a new run for this test"
          >
            {startRunMutation.isPending ? "Starting…" : "Start run"}
          </Button>
        </div>
      </div>

      {startRunMutation.isError && (
        <div
          role="alert"
          className="mb-4 rounded-md bg-alert/10 px-3 py-2 text-sm text-alert"
        >
          Failed to start run. Try again.
        </div>
      )}

      {/* Config */}
      <div className="mb-6 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900">
        <div className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-medium text-zinc-300">Configuration</h2>
        </div>
        {testLoading ? (
          <div className="space-y-0 divide-y divide-zinc-800">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-2.5">
                <Skeleton className="h-4 w-24 bg-zinc-800" />
                <Skeleton className="h-4 w-32 bg-zinc-800" />
              </div>
            ))}
          </div>
        ) : test ? (
          <>
            <ConfigRow label="Target URL" value={test.script_uri ?? "inline script"} />
            <ConfigRow label="Virtual users (VUs)" value={test.config.vus} />
            <ConfigRow label="Duration" value={`${test.config.duration_seconds}s`} />
          </>
        ) : null}
      </div>

      {/* Script preview */}
      {(testLoading || test?.script_inline) && (
        <div className="mb-6 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900">
          <div className="border-b border-zinc-800 px-4 py-3">
            <h2 className="text-sm font-medium text-zinc-300">
              Script
              <span className="ml-2 font-mono text-xs text-zinc-500">
                read-only
              </span>
            </h2>
          </div>
          {testLoading ? (
            <div className="px-4 py-3">
              <Skeleton className="h-32 w-full rounded-lg bg-zinc-800" />
            </div>
          ) : (
            <pre className="max-h-64 overflow-auto px-4 py-3 font-mono text-xs text-zinc-300">
              {test?.script_inline}
            </pre>
          )}
        </div>
      )}

      {/* Run history */}
      <div className="overflow-hidden rounded-xl border border-zinc-800">
        <div className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-medium text-zinc-300">Run history</h2>
        </div>
        {runsError ? (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-alert">Failed to load runs.</p>
          </div>
        ) : (
          <div className="px-0 py-0">
            <RunList
              runs={runs}
              product={product}
              isLoading={runsLoading || testLoading}
            />
          </div>
        )}
      </div>
    </div>
  );
}
