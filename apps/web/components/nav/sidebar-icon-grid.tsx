"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import { PRODUCTS, type Product } from "@/lib/products";
import { cn } from "@/lib/utils";

interface SidebarIconGridProps {
  current: Product;
}

/**
 * Compact 4-column icon grid for sidebar product switcher.
 * Shows accent color dot indicator + accent fill on hover.
 * Preserves product switcher parity — sets ?product= query + body attribute.
 */
export function SidebarIconGrid({ current }: SidebarIconGridProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const reduced = useReducedMotion();

  function select(id: Product) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("product", id);
    router.push(`/runs?${params.toString()}`);
    document.body.setAttribute("data-product", id);
  }

  return (
    <div className="px-3 pb-3">
      <p className="mb-1.5 px-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
        Products
      </p>
      <div
        className="grid grid-cols-4 gap-1"
        role="listbox"
        aria-label="Product switcher (compact)"
      >
        {PRODUCTS.map((product) => {
          const Icon = product.icon;
          const isActive = current === product.id;

          return (
            <div key={product.id} role="option" aria-selected={isActive}>
              <motion.button
                type="button"
                onClick={() => select(product.id)}
                title={product.label}
                aria-label={`Switch to ${product.label}`}
                className={cn(
                  "relative flex w-full flex-col items-center gap-0.5 rounded-md p-2 transition-colors",
                  isActive
                    ? "bg-zinc-800"
                    : "text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-300"
                )}
                style={isActive ? { color: product.accent } : undefined}
                whileTap={reduced ? undefined : { scale: 0.93 }}
              >
                {/* Active accent indicator dot */}
                <span
                  className={cn(
                    "absolute right-1 top-1 h-1.5 w-1.5 rounded-full transition-opacity",
                    isActive ? "opacity-100" : "opacity-0"
                  )}
                  style={{ backgroundColor: product.accent }}
                  aria-hidden="true"
                />
                <Icon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                <span className="max-w-full truncate text-center text-[9px] leading-tight">
                  {/* Short label — first word only to fit grid */}
                  {product.label.split(" ")[0]}
                </span>
              </motion.button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
