"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { PRODUCTS, type Product } from "@/lib/products";

/**
 * Left-sidebar vertical pill list of products.
 *
 * - Sidebar nav stays signal-toned (#18F2C3) — this component only highlights the
 *   active product pill with the product accent.
 * - Sets ?product=<id> in the URL query and updates [data-product] on <body>
 *   so the CSS var --accent-current resolves correctly for page header + charts.
 */
export function ProductSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const current = (searchParams.get("product") ?? "load") as Product;

  function select(id: Product) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("product", id);
    // Navigate to runs list filtered by the chosen product
    router.push(`/runs?${params.toString()}`);
  }

  // Sync body attribute as a side effect — never touch the DOM during render.
  useEffect(() => {
    document.body.setAttribute("data-product", current);
  }, [current]);

  return (
    <div className="px-3 pb-3">
      <p className="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
        Products
      </p>
      <ul className="flex flex-col gap-0.5" role="listbox" aria-label="Product switcher">
        {PRODUCTS.map((product) => {
          const Icon = product.icon;
          const isActive = current === product.id && pathname.startsWith("/runs");

          return (
            <li key={product.id} role="option" aria-selected={isActive}>
              <button
                type="button"
                onClick={() => select(product.id)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "text-zinc-100"
                    : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
                )}
                style={
                  isActive
                    ? {
                        backgroundColor: `${product.accent}22`,
                        color: product.accent,
                      }
                    : undefined
                }
                aria-label={`Switch to ${product.label}`}
              >
                <Icon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                {product.label}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
