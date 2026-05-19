/**
 * Command palette registry and search index.
 *
 * Static actions are defined here.
 * Dynamic entries (recent runs, products) are injected at runtime via
 * buildCommandIndex().
 */

import type { TestRun } from "@testlyn/shared";
import { PRODUCTS } from "@/lib/products";

export type CommandGroup =
  | "navigate"
  | "products"
  | "runs"
  | "actions"
  | "settings";

export interface CommandItem {
  id: string;
  group: CommandGroup;
  label: string;
  /** Subtitle shown in palette (e.g. product name, status). */
  subtitle?: string;
  /** href — if set, palette navigates on select. */
  href?: string;
  /** callback — if set, called on select instead of navigate. */
  action?: () => void;
  /** Accent hex for the dot indicator. */
  accent?: string;
  /** Keywords used by fuzzy search. */
  keywords: string[];
}

// ─── Static commands ──────────────────────────────────────────────────────────

export const STATIC_COMMANDS: CommandItem[] = [
  // Navigation
  {
    id: "nav-projects",
    group: "navigate",
    label: "Go to Projects",
    keywords: ["projects", "home", "overview"],
    href: "/projects",
  },
  {
    id: "nav-chat",
    group: "navigate",
    label: "Open Chat",
    keywords: ["chat", "copilot", "assistant", "agent", "ai"],
    href: "/chat",
  },
  {
    id: "nav-settings",
    group: "navigate",
    label: "Go to Settings",
    keywords: ["settings", "account", "profile", "preferences"],
    href: "/settings",
  },
  {
    id: "nav-api-keys",
    group: "navigate",
    label: "Open API Keys",
    keywords: ["api keys", "key", "token", "secret"],
    href: "/settings/api-keys",
  },
  {
    id: "nav-billing",
    group: "navigate",
    label: "Go to Billing",
    keywords: ["billing", "plan", "subscription", "stripe", "invoice"],
    href: "/settings/billing",
  },
  {
    id: "nav-members",
    group: "navigate",
    label: "Invite Team Member",
    keywords: ["invite", "team", "member", "people", "org"],
    href: "/settings/members",
  },
  {
    id: "nav-status",
    group: "navigate",
    label: "System Status",
    keywords: ["status", "uptime", "health", "incident"],
    href: "/status",
  },
  // Actions
  {
    id: "action-new-test",
    group: "actions",
    label: "Create New Test",
    keywords: ["new test", "create", "start", "add"],
    href: "/projects",
  },
  {
    id: "action-sign-out",
    group: "actions",
    label: "Sign Out",
    keywords: ["sign out", "logout", "log out", "exit"],
  },
];

// ─── Dynamic index builder ────────────────────────────────────────────────────

export function buildCommandIndex(
  recentRuns: TestRun[],
  signOut: () => void
): CommandItem[] {
  // Product navigation entries
  const productCommands: CommandItem[] = PRODUCTS.map((p) => ({
    id: `product-${p.id}`,
    group: "products" as CommandGroup,
    label: `${p.label} Testing`,
    subtitle: "Product",
    keywords: [p.label, p.id, "product", "testing"],
    href: `/runs?product=${p.id}`,
    accent: p.accent,
  }));

  // Recent runs (last 20)
  const runCommands: CommandItem[] = recentRuns.slice(0, 20).map((run) => ({
    id: `run-${run.id}`,
    group: "runs" as CommandGroup,
    label: run.id,
    subtitle: `${run.state} · ${run.product}`,
    keywords: [run.id, run.state, run.product, "run"],
    href: `/runs/${run.id}`,
    accent:
      PRODUCTS.find((p) => p.id === run.product)?.accent ?? "#3730A3",
  }));

  // Wire up sign-out action
  const staticWithAction = STATIC_COMMANDS.map((cmd) => {
    if (cmd.id === "action-sign-out") {
      return { ...cmd, action: signOut };
    }
    return cmd;
  });

  return [...staticWithAction, ...productCommands, ...runCommands];
}
