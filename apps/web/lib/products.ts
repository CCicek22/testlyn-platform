/**
 * Client-side product registry.
 * Accent colors are frozen per CLAUDE.md §4 — do not change without user approval.
 */

import { Zap, FlaskConical, Eye } from "lucide-react";
import type { ElementType } from "react";

export type Product = "load" | "functional" | "a11y";

export interface ProductMeta {
  readonly id: Product;
  readonly label: string;
  /** Frozen hex from CLAUDE.md §4 */
  readonly accent: string;
  readonly icon: ElementType;
  readonly available: boolean;
}

export const PRODUCTS: readonly ProductMeta[] = [
  {
    id: "load",
    label: "Load Testing",
    accent: "#3730A3",
    icon: Zap,
    available: true,
  },
  {
    id: "functional",
    label: "Functional",
    accent: "#8B5CF6",
    icon: FlaskConical,
    available: true,
  },
  {
    id: "a11y",
    label: "Accessibility",
    accent: "#14B8A6",
    icon: Eye,
    available: true,
  },
] as const;

export function getProduct(id: string): ProductMeta {
  return PRODUCTS.find((p) => p.id === id) ?? PRODUCTS[0]!;
}

export function isProduct(val: string): val is Product {
  return PRODUCTS.some((p) => p.id === val);
}
