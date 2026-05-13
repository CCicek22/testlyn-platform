"use client";

import { RunRow } from "@/components/runs/run-row";
import { getProduct, type Product } from "@/lib/products";
import type { TestRun } from "@testlyn/shared";

interface RunListProps {
  runs: TestRun[];
  product: Product;
  isLoading?: boolean;
}

function LoadHeader() {
  return (
    <>
      <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
        p95
      </th>
      <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Error rate
      </th>
    </>
  );
}

function FunctionalHeader() {
  return (
    <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
      Results
    </th>
  );
}

function A11yHeader() {
  return (
    <>
      <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
        URLs scanned
      </th>
      <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Violations
      </th>
    </>
  );
}

export function RunList({ runs, product, isLoading = false }: RunListProps) {
  const meta = getProduct(product);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-sm text-zinc-500">
        Loading runs…
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-sm text-zinc-400">No {meta.label} runs yet.</p>
        <p className="mt-1 text-xs text-zinc-600">
          Trigger a test run from any project to see it here.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-zinc-800 bg-zinc-900/50">
            {/* accent strip column */}
            <th scope="col" className="w-1 px-0" aria-hidden="true" />
            <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Run ID
            </th>
            <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Started
            </th>
            <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Duration
            </th>
            {product === "load" && <LoadHeader />}
            {product === "functional" && <FunctionalHeader />}
            {product === "a11y" && <A11yHeader />}
            <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
              State
            </th>
            <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <RunRow key={run.id} run={run} product={product} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
