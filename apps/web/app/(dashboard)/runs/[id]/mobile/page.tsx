import { getProduct } from "@/lib/products";
import { Smartphone } from "lucide-react";

const PRODUCT = getProduct("mobile");

// Future-phase placeholder — the backend stub for this product returns 501
// NOT_IMPLEMENTED, so there is nothing to fetch yet. Static copy mirrors the
// stub's detail/available_in fields.
export default function MobileRunPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 py-16 text-center">
      <div
        className="mb-6 inline-flex h-16 w-16 items-center justify-center rounded-2xl"
        style={{ backgroundColor: `${PRODUCT.accent}1A`, color: PRODUCT.accent }}
        aria-hidden="true"
      >
        <Smartphone className="h-8 w-8" />
      </div>

      <h1 className="mb-2 text-2xl font-bold tracking-tight text-zinc-100">
        {PRODUCT.label}
      </h1>

      <span
        className="mb-6 inline-block rounded-full px-3 py-0.5 text-xs font-semibold"
        style={{ backgroundColor: `${PRODUCT.accent}22`, color: PRODUCT.accent }}
      >
        Phase 4 GA
      </span>

      <p className="max-w-md text-sm text-zinc-400">
        Mobile performance testing is not yet available.
      </p>
    </div>
  );
}
