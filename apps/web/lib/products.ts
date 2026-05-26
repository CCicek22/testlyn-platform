/**
 * Client-side product registry.
 * Accent colors map QA product surfaces to the current Testlyn signal palette.
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
  /** Product signal color. */
  readonly accent: string;
  readonly icon: ElementType;
  readonly available: boolean;
}

export const PRODUCTS: readonly ProductMeta[] = [
  {
    id: "load",
    label: "Load Testing",
    accent: "#18F2C3",
    icon: Zap,
    available: true,
  },
  {
    id: "functional",
    label: "Functional",
    accent: "#7CFFE1",
    icon: FlaskConical,
    available: true,
  },
  {
    id: "a11y",
    label: "Accessibility",
    accent: "#5CFF93",
    icon: Eye,
    available: true,
  },
  {
    id: "synthetic_data",
    label: "Synthetic Data",
    accent: "#FFD166",
    icon: Database,
    available: true,
  },
  {
    id: "api_contract",
    label: "API Contract",
    accent: "#3DDCFF",
    icon: GitCompare,
    available: true,
  },
  {
    id: "security",
    label: "Security",
    accent: "#FF4D6D",
    icon: Shield,
    available: true,
  },
  // Phase 4 products — available: false renders a "Phase 4 GA" badge in sidebar
  {
    id: "mobile",
    label: "Mobile",
    accent: "#8BB8FF",
    icon: Smartphone,
    available: false,
  },
  {
    id: "visual",
    label: "Visual Regression",
    accent: "#D49BFF",
    icon: ScanEye,
    available: false,
  },
  {
    id: "rum",
    label: "Real User Monitoring",
    accent: "#3DDCFF",
    icon: Users,
    available: false,
  },
  {
    id: "tdm",
    label: "Test Data Management",
    accent: "#FF9F6E",
    icon: FolderSync,
    available: false,
  },
  {
    id: "qa_maturity",
    label: "QA Maturity",
    accent: "#5CFF93",
    icon: ClipboardCheck,
    available: false,
  },
  {
    id: "eng_analytics",
    label: "Engineering Analytics",
    accent: "#FFD166",
    icon: BarChart3,
    available: false,
  },
  {
    id: "cicd_insights",
    label: "CI/CD Insights",
    accent: "#FF7AB6",
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
