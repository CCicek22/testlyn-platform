"use client";

import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { RunList } from "@/components/runs/run-list";
import { PRODUCTS, getProduct, isProduct, type Product } from "@/lib/products";
import type { TestRun } from "@testlyn/shared";

export default function RunsPage() {
  const searchParams = useSearchParams();
  const rawProduct = searchParams.get("product") ?? "load";
  const product: Product = isProduct(rawProduct) ? rawProduct : "load";
  const meta = getProduct(product);

  const { data, isLoading, error } = useQuery<TestRun[]>({
    queryKey: ["runs", product],
    queryFn: () => api.runs.list(product, 50),
  });

  return (
    <div
      className="flex flex-col min-h-full"
      data-product={product}
    >
      {/* Page header strip — uses product accent color */}
      <div
        className="border-b border-zinc-800 px-6 py-4"
        style={{ borderTopColor: meta.accent, borderTopWidth: 3 }}
      >
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h1
                className="text-lg font-bold tracking-tight text-zinc-100"
                style={{ color: meta.accent }}
              >
                {meta.label}
              </h1>
              <span className="text-lg font-bold text-zinc-100">Runs</span>
            </div>
            <p className="mt-0.5 text-sm text-zinc-500">
              Last 50 runs across all projects
            </p>
          </div>

          {/* Product pills */}
          <div className="hidden items-center gap-1.5 sm:flex">
            {PRODUCTS.map((p) => {
              const isActive = p.id === product;
              return (
                <a
                  key={p.id}
                  href={`/runs?product=${p.id}`}
                  className="rounded-full px-3 py-1 text-xs font-medium transition-colors"
                  style={
                    isActive
                      ? { backgroundColor: `${p.accent}22`, color: p.accent }
                      : { color: "#71717A" }
                  }
                  aria-current={isActive ? "page" : undefined}
                >
                  {p.label}
                </a>
              );
            })}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 px-6 py-6">
        {error ? (
          <div role="alert" className="rounded-md bg-alert/10 px-4 py-3 text-sm text-alert">
            Failed to load runs. Check your connection and try again.
          </div>
        ) : (
          <RunList runs={data ?? []} product={product} isLoading={isLoading} />
        )}
      </div>
    </div>
  );
}
