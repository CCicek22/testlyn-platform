"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV_TABS = [
  { label: "Account", href: "/settings/account" },
  { label: "API Keys", href: "/settings/api-keys" },
  { label: "Billing", href: "/settings/billing" },
  { label: "Members", href: "/settings/members" },
] as const;

export function SettingsNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-0.5" aria-label="Settings navigation">
      {NAV_TABS.map(({ label, href }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "rounded-md px-3 py-2 text-sm font-medium transition-colors",
            pathname === href
              ? "bg-primary/10 text-primary"
              : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
          )}
          aria-current={pathname === href ? "page" : undefined}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
