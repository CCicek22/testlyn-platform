"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { Test } from "@testlyn/shared";

function TestRow({ test }: { test: Test }) {
  return (
    <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-zinc-100">{test.name}</p>
        <p className="text-xs text-zinc-500">
          {test.config.vus} VUs · {test.config.duration_seconds}s ·{" "}
          {new Date(test.created_at).toLocaleDateString()}
        </p>
      </div>
      <div className="ml-4 flex items-center gap-2">
        <Link href={`/tests/${test.id}/edit`}>
          <Button variant="ghost" size="sm" className="text-zinc-400 hover:text-zinc-100">
            Edit
          </Button>
        </Link>
        <Link href={`/tests/${test.id}`}>
          <Button variant="outline" size="sm" className="border-zinc-700 text-zinc-300 hover:text-zinc-100">
            Runs
          </Button>
        </Link>
      </div>
    </div>
  );
}

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const { data: tests, isLoading, error } = useQuery<Test[]>({
    queryKey: ["tests", projectId],
    queryFn: () => api.projects.tests(projectId),
    enabled: !!projectId,
  });

  const testList = tests ?? [];

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/projects"
            className="text-zinc-400 hover:text-zinc-100"
            aria-label="Back to projects"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M19 12H5M12 5l-7 7 7 7" />
            </svg>
          </Link>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
            Project
          </h1>
          <Badge className="border-zinc-700 bg-zinc-800 font-mono text-xs text-zinc-400">
            {projectId}
          </Badge>
        </div>

        <Link href={`/tests/new?project=${projectId}`}>
          <Button>
            <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New test
          </Button>
        </Link>
      </div>

      <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900">
        <div className="border-b border-zinc-800 px-4 py-3">
          <h2 className="text-sm font-medium text-zinc-300">Tests</h2>
        </div>

        {isLoading && (
          <div className="divide-y divide-zinc-800">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-3">
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-48 bg-zinc-800" />
                  <Skeleton className="h-3 w-32 bg-zinc-800" />
                </div>
                <Skeleton className="h-8 w-24 bg-zinc-800" />
              </div>
            ))}
          </div>
        )}

        {error && (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-alert">Failed to load tests.</p>
          </div>
        )}

        {!isLoading && !error && testList.length === 0 && (
          <div className="flex flex-col items-center py-16 text-center">
            <svg
              className="mb-4 h-8 w-8 text-zinc-600"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <path d="M9 12h6M9 16h6M13 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-5-5z" />
              <path d="M13 4v5h5" />
            </svg>
            <p className="text-sm text-zinc-400">No tests in this project.</p>
            <Link href={`/tests/new?project=${projectId}`} className="mt-4">
              <Button size="sm">Create first test</Button>
            </Link>
          </div>
        )}

        {!isLoading && !error && testList.length > 0 && (
          <div>
            {testList.map((test) => (
              <TestRow key={test.id} test={test} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
