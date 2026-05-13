"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getProduct } from "@/lib/products";
import { ScanEye } from "lucide-react";

const PRODUCT = getProduct("visual");

async function fetchVisualScan(runId: string) {
  const res = await fetch(`/api/v1/products/visual/scans/${runId}`);
  return res.json() as Promise<{ code: string; detail: string; available_in: string }>;
}

export default function VisualRunPage() {
  const { id } = useParams<{ id: string }>();

  const { data } = useQuery({
    queryKey: ["visual-scan", id],
    queryFn: () => fetchVisualScan(id),
    retry: false,
  });

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 py-16 text-center">
      <div
        className="mb-6 inline-flex h-16 w-16 items-center justify-center rounded-2xl"
        style={{ backgroundColor: `${PRODUCT.accent}1A`, color: PRODUCT.accent }}
        aria-hidden="true"
      >
        <ScanEye className="h-8 w-8" />
      </div>

      <h1 className="mb-2 text-2xl font-bold tracking-tight text-zinc-100">
        {PRODUCT.label}
      </h1>

      <span
        className="mb-6 inline-block rounded-full px-3 py-0.5 text-xs font-semibold"
        style={{ backgroundColor: `${PRODUCT.accent}22`, color: PRODUCT.accent }}
      >
        {data?.available_in ?? "Phase 4 GA"}
      </span>

      <p className="max-w-md text-sm text-zinc-400">
        {data?.detail ?? "This product is not yet available."}
      </p>
    </div>
  );
}
