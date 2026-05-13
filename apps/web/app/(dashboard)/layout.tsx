"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { LogoPulse } from "@/components/brand/logo-pulse";
import { useAuth } from "@/components/auth/auth-provider";
import { signOutUser } from "@/lib/firebase";
import { cn } from "@/lib/utils";
import { ProductSwitcher } from "@/components/nav/product-switcher";

const NAV_ITEMS = [
  {
    label: "Projects",
    href: "/projects",
    icon: (
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
        <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      </svg>
    ),
  },
] as const;

function SidebarLink({
  href,
  icon,
  label,
  active,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-primary/10 text-primary"
          : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
      )}
      aria-current={active ? "page" : undefined}
    >
      {icon}
      {label}
    </Link>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  async function handleSignOut() {
    await signOutUser();
    window.location.href = "/login";
  }

  return (
    <div className="flex min-h-screen bg-dark text-zinc-100">
      {/* Sidebar */}
      <aside className="hidden w-56 flex-shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 lg:flex">
        <div className="flex h-14 items-center border-b border-zinc-800 px-4">
          <Link href="/projects" aria-label="Testlyn home">
            <LogoPulse size={22} />
          </Link>
        </div>

        <nav className="flex flex-1 flex-col gap-1 p-3" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => (
            <SidebarLink
              key={item.href}
              href={item.href}
              icon={item.icon}
              label={item.label}
              active={pathname.startsWith(item.href)}
            />
          ))}

          <div className="mt-3 border-t border-zinc-800 pt-3">
            <ProductSwitcher />
          </div>
        </nav>

        {/* User menu */}
        <div className="border-t border-zinc-800 p-3">
          <div className="relative">
            <button
              onClick={() => setMenuOpen((o) => !o)}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              <span
                className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/20 text-xs font-semibold text-primary"
                aria-hidden="true"
              >
                {user?.email?.[0]?.toUpperCase() ?? "U"}
              </span>
              <span className="min-w-0 flex-1 truncate text-left">
                {user?.email ?? "dev@testlyn.io"}
              </span>
              <svg
                className="h-4 w-4 flex-shrink-0"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                aria-hidden="true"
              >
                <path d="M8 9l4-4 4 4M8 15l4 4 4-4" />
              </svg>
            </button>

            {menuOpen && (
              <div
                className="absolute bottom-full left-0 mb-1 w-full rounded-md border border-zinc-700 bg-zinc-900 py-1 shadow-lg"
                role="menu"
              >
                <button
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
                  onClick={handleSignOut}
                  role="menuitem"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
                  </svg>
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile header */}
        <header className="flex h-14 items-center border-b border-zinc-800 px-4 lg:hidden">
          <Link href="/projects" aria-label="Testlyn home">
            <LogoPulse size={20} wordmark={false} />
          </Link>
          <span className="ml-2 text-sm font-semibold text-zinc-100">Testlyn</span>
        </header>

        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
