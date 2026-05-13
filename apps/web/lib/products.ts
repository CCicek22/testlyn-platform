/**
 * Client-side product registry.
 * Accent colors are frozen per CLAUDE.md §4 — do not change without user approval.
 */

import {
  Zap,
  FlaskConical,
  Eye,
  Database,
  GitCompare,
  Shield,
  Smartphone,
  ScanEye,
  Users,
  FolderSync,
  ClipboardCheck,
  BarChart3,
  GitBranch,
} from "lucide-react";
import type { ElementType } from "react";

export type Product =
  | "load"
  | "functional"
  | "a11y"
  | "synthetic_data"
  | "api_contract"
  | "security"
  | "mobile"
  | "visual"
  | "rum"
  | "tdm"
  | "qa_maturity"
  | "eng_analytics"
  | "cicd_insights";

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
  {
    id: "synthetic_data",
    label: "Synthetic Data",
    /** Frozen per CLAUDE.md §4 */
    accent: "#F59E0B",
    icon: Database,
    available: true,
  },
  {
    id: "api_contract",
    label: "API Contract",
    /** Frozen per CLAUDE.md §4 */
    accent: "#06B6D4",
    icon: GitCompare,
    available: true,
  },
  {
    id: "security",
    label: "Security",
    /** Frozen per CLAUDE.md §4 */
    accent: "#DC2626",
    icon: Shield,
    available: true,
  },
  // Phase 4 products — available: false renders a "Phase 4 GA" badge in sidebar
  {
    id: "mobile",
    label: "Mobile",
    accent: "#6366F1",
    icon: Smartphone,
    available: false,
  },
  {
    id: "visual",
    label: "Visual Regression",
    accent: "#A855F7",
    icon: ScanEye,
    available: false,
  },
  {
    id: "rum",
    label: "Real User Monitoring",
    accent: "#0EA5E9",
    icon: Users,
    available: false,
  },
  {
    id: "tdm",
    label: "Test Data Management",
    accent: "#F97316",
    icon: FolderSync,
    available: false,
  },
  {
    id: "qa_maturity",
    label: "QA Maturity",
    accent: "#22C55E",
    icon: ClipboardCheck,
    available: false,
  },
  {
    id: "eng_analytics",
    label: "Engineering Analytics",
    accent: "#EAB308",
    icon: BarChart3,
    available: false,
  },
  {
    id: "cicd_insights",
    label: "CI/CD Insights",
    accent: "#EC4899",
    icon: GitBranch,
    available: false,
  },
] as const;

export function getProduct(id: string): ProductMeta {
  return PRODUCTS.find((p) => p.id === id) ?? PRODUCTS[0]!;
}

export function isProduct(val: string): val is Product {
  return PRODUCTS.some((p) => p.id === val);
}
