"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { getProduct, type Product } from "@/lib/products";
import { RunList } from "@/components/runs/run-list";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/auth/auth-provider";
import type { TestRun, MeResponse } from "@testlyn/shared";

export function ProductContent({ product }: { product: Product }) {
  const router = useRouter();
  const { user } = useAuth();
  const meta = getProduct(product);

  const { data: me } = useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => api.me(),
    enabled: user != null,
    staleTime: 5 * 60_000,
  });
  const orgId = me?.memberships?.[0]?.org_id ?? null;

  const { data: runs, isLoading, error } = useQuery<TestRun[]>({
    queryKey: ["runs", product],
    queryFn: () => api.runs.list(product, 50),
    enabled: user != null,
  });

  const ProductIcon = meta.icon;

  return (
    <div className="flex min-h-full flex-col" data-product={product}>
      <div
        className="border-b border-zinc-800 px-6 py-4"
        style={{ borderTopColor: meta.accent, borderTopWidth: 3 }}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg"
              style={{ backgroundColor: `${meta.accent}22`, color: meta.accent }}
              aria-hidden="true"
            >
              <ProductIcon className="h-5 w-5" />
            </div>
            <div>
              <h1
                className="text-lg font-bold tracking-tight"
                style={{ color: meta.accent }}
              >
                {meta.label}
              </h1>
              <p className="text-xs text-zinc-500">Last 50 runs</p>
            </div>
          </div>

          <Button
            onClick={() => router.push("/tests/new")}
            aria-label={`Create new ${meta.label} test`}
          >
            <svg
              className="mr-2 h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              aria-hidden="true"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>
            New test
          </Button>
        </div>
      </div>

      <div className="flex-1 px-6 py-6">
        {error ? (
          <div
            role="alert"
            className="rounded-md bg-alert/10 px-4 py-3 text-sm text-alert"
          >
            Failed to load runs. Check your connection and try again.
          </div>
        ) : (
          <RunList runs={runs ?? []} product={product} isLoading={isLoading} />
        )}
      </div>

      {orgId != null && (runs ?? []).length > 0 && (
        <div className="border-t border-zinc-800 px-6 py-4">
          <Link
            href={`/runs?product=${product}`}
            className="text-sm text-zinc-400 hover:text-zinc-100"
          >
            View all {meta.label.toLowerCase()} runs →
          </Link>
        </div>
      )}
    </div>
  );
}
