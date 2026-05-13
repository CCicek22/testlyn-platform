import { notFound } from "next/navigation";
import { getProduct, isProduct } from "@/lib/products";

interface Props {
  params: Promise<{ product: string }>;
}

export default async function ComingSoonPage({ params }: Props) {
  const { product: productId } = await params;

  if (!isProduct(productId)) {
    notFound();
  }

  const product = getProduct(productId);

  if (product.available) {
    // Redirect away — product is live, this page shouldn't be shown
    notFound();
  }

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 py-16 text-center">
      <div
        className="mb-6 inline-flex h-16 w-16 items-center justify-center rounded-2xl"
        style={{ backgroundColor: `${product.accent}1A`, color: product.accent }}
        aria-hidden="true"
      >
        <product.icon className="h-8 w-8" />
      </div>

      <h1 className="mb-2 text-2xl font-bold tracking-tight text-zinc-100">
        {product.label}
      </h1>

      <span
        className="mb-6 inline-block rounded-full px-3 py-0.5 text-xs font-semibold"
        style={{ backgroundColor: `${product.accent}22`, color: product.accent }}
      >
        Phase 4 GA
      </span>

      <p className="max-w-md text-sm text-zinc-400">
        This product is on the Phase 4 roadmap and is not yet available.
        Sign up to be notified when it launches.
      </p>
    </div>
  );
}
