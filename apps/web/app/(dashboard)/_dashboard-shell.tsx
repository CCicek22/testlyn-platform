"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LogoPulse } from "@/components/brand/logo-pulse";
import { useAuth } from "@/components/auth/auth-provider";
import { api } from "@/lib/api-client";
import { signOutUser } from "@/lib/firebase";
import type { MeResponse } from "@testlyn/shared";
import { cn } from "@/lib/utils";
import { ProductSwitcher } from "@/components/nav/product-switcher";
import { SidebarIconGrid } from "@/components/nav/sidebar-icon-grid";
import { useCmdk } from "@/lib/use-cmdk";
import { isProduct } from "@/lib/products";

// Dynamic import keeps cmdk + framer-motion out of the initial JS bundle
const CommandPalette = dynamic(
  () =>
    import("@/components/cmdk/command-palette").then(
      (m) => m.CommandPalette
    ),
  { ssr: false }
);

const ProductTour = dynamic(
  () =>
    import("@/components/onboarding/product-tour").then(
      (m) => m.ProductTour
    ),
  { ssr: false }
);

const NAV_ITEMS = [
  {
    label: "Projects",
    href: "/projects",
    icon: (
      <svg
        className="h-4 w-4"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
        <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      </svg>
    ),
  },
  {
    label: "Chat",
    href: "/chat",
    icon: (
      <svg
        className="h-4 w-4"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
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
        "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-all duration-200",
        active
          ? "trace-glow bg-primary/15 text-primary"
          : "text-zinc-400 hover:bg-primary/10 hover:text-zinc-100"
      )}
      aria-current={active ? "page" : undefined}
    >
      {icon}
      {label}
    </Link>
  );
}

// ─── Kbd hint for Cmd+K ───────────────────────────────────────────────────────

function CmdKHint({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-md border border-zinc-800 bg-white/5 px-3 py-1.5 text-xs text-zinc-500 backdrop-blur-xl transition-colors hover:bg-primary/10 hover:text-primary"
      aria-label="Open command palette"
    >
      <svg
        className="h-3.5 w-3.5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="8" />
        <path d="m21 21-4.35-4.35" />
      </svg>
      <span className="flex-1 text-left">Search…</span>
      <kbd className="rounded border border-zinc-700 px-1 py-0.5 text-[10px]">
        ⌘K
      </kbd>
    </button>
  );
}

// ─── Sidebar mode toggle ──────────────────────────────────────────────────────

function SidebarModeToggle({
  compact,
  onToggle,
}: {
  compact: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      title={compact ? "Switch to list view" : "Switch to compact grid"}
      className="flex items-center justify-center rounded-md p-1 text-zinc-600 transition-colors hover:bg-primary/10 hover:text-primary"
      aria-label={compact ? "Switch to list view" : "Switch to compact grid"}
    >
      {compact ? (
        // List icon
        <svg
          className="h-3.5 w-3.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <line x1="8" y1="6" x2="21" y2="6" />
          <line x1="8" y1="12" x2="21" y2="12" />
          <line x1="8" y1="18" x2="21" y2="18" />
          <line x1="3" y1="6" x2="3.01" y2="6" />
          <line x1="3" y1="12" x2="3.01" y2="12" />
          <line x1="3" y1="18" x2="3.01" y2="18" />
        </svg>
      ) : (
        // Grid icon
        <svg
          className="h-3.5 w-3.5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <rect x="3" y="3" width="7" height="7" />
          <rect x="14" y="3" width="7" height="7" />
          <rect x="3" y="14" width="7" height="7" />
          <rect x="14" y="14" width="7" height="7" />
        </svg>
      )}
    </button>
  );
}

// ─── Layout ───────────────────────────────────────────────────────────────────

export default function DashboardShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, loading } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [compactSidebar, setCompactSidebar] = useState(false);

  const { open: paletteOpen, setOpen: setPaletteOpen, toggle: togglePalette } = useCmdk();

  const currentProduct = searchParams.get("product") ?? "load";
  const safeProduct = isProduct(currentProduct) ? currentProduct : "load";

  // Membership lookup powers the org-guard below. Shares the ["me"] query key
  // with the dashboard pages, so this adds no extra network round-trip.
  const { data: me, isLoading: meLoading } = useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => api.me(),
    enabled: user != null,
    staleTime: 5 * 60_000,
  });

  const onOnboarding = pathname === "/onboarding";
  const hasNoOrg = me != null && me.memberships.length === 0;

  // Client-side auth guard: redirect signed-out users before any data-fetching
  // child renders. Avoids the flash of dashboard chrome + a stream of 401s
  // while React Query mounts and hits the API anonymously.
  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  // Org guard: a brand-new user with zero memberships would otherwise dead-end
  // on empty dashboard skeletons. Send them to onboarding; once they have an
  // org, keep them out of onboarding.
  useEffect(() => {
    if (loading || !user || !me) return;
    if (hasNoOrg && !onOnboarding) {
      router.replace("/onboarding");
    } else if (!hasNoOrg && onOnboarding) {
      router.replace("/projects");
    }
  }, [loading, user, me, hasNoOrg, onOnboarding, router]);

  if (!loading && !user) {
    return null;
  }

  const loaderScreen = (
    <div className="flex min-h-screen items-center justify-center bg-dark">
      <LogoPulse size={28} wordmark={false} />
    </div>
  );

  // Onboarding renders on a clean, sidebar-free canvas (the page owns its
  // centered card layout). No dead nav links for a user without an org yet.
  // Gate on membership resolution: while `me` is still loading — or for an
  // org'd user who opened /onboarding directly — show the loader so the
  // redirect guard fires without flashing the create-org UI. Only a confirmed
  // zero-org user reaches the onboarding layout.
  if (onOnboarding) {
    if (meLoading || (me != null && me.memberships.length > 0)) {
      return loaderScreen;
    }
    return (
      <div className="flex min-h-screen flex-col bg-dark text-zinc-100">
        <header className="flex h-14 items-center border-b border-zinc-800 px-4 sm:px-6">
          <LogoPulse size={22} />
        </header>
        <main className="flex flex-1 items-center justify-center px-4 py-12 sm:px-6">
          {children}
        </main>
      </div>
    );
  }

  // Hold the dashboard chrome until membership state is known (or while a
  // redirect to onboarding is imminent) so no-org users never see the empty
  // skeleton flash.
  if (user && (meLoading || hasNoOrg)) {
    return loaderScreen;
  }

  async function handleSignOut() {
    await signOutUser();
    window.location.href = "/login";
  }

  return (
    <div className="flex min-h-screen bg-dark text-zinc-100">
      {/* Command palette (portaled, keyboard-driven) */}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />

      {/* Onboarding tour (fixed bottom-right) */}
      <ProductTour product={safeProduct} />

      {/* Sidebar */}
      <aside className="hidden w-56 flex-shrink-0 flex-col border-r border-zinc-800 bg-zinc-950/80 backdrop-blur-2xl lg:flex">
        <div className="flex h-14 items-center border-b border-zinc-800 px-4">
          <Link href="/projects" aria-label="Testlyn home">
            <LogoPulse size={22} />
          </Link>
        </div>

        <nav
          className="flex flex-1 flex-col gap-1 p-3"
          aria-label="Main navigation"
        >
          {NAV_ITEMS.map((item) => (
            <SidebarLink
              key={item.href}
              href={item.href}
              icon={item.icon}
              label={item.label}
              active={pathname.startsWith(item.href)}
            />
          ))}

          {/* Cmd+K hint */}
          <div className="mt-1">
            <CmdKHint onClick={togglePalette} />
          </div>

          {/* Products section with mode toggle */}
          <div className="mt-3 border-t border-zinc-800 pt-3">
            <div className="mb-1 flex items-center justify-end px-1">
              <SidebarModeToggle
                compact={compactSidebar}
                onToggle={() => setCompactSidebar((c) => !c)}
              />
            </div>
            {compactSidebar ? (
              <SidebarIconGrid current={safeProduct} />
            ) : (
              <ProductSwitcher />
            )}
          </div>
        </nav>

        {/* User menu */}
        <div className="border-t border-zinc-800 p-3">
          <div className="relative">
            <button
              onClick={() => setMenuOpen((o) => !o)}
              className="flex w-full items-center gap-2.5 rounded-md border border-transparent px-3 py-2 text-sm text-zinc-400 transition-colors hover:border-primary/20 hover:bg-primary/10 hover:text-zinc-100"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              <span
                className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border border-primary/30 bg-primary/15 text-xs font-semibold text-primary"
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
                className="liquid-glass absolute bottom-full left-0 mb-1 w-full rounded-md py-1"
                role="menu"
              >
                <button
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-zinc-400 hover:bg-primary/10 hover:text-zinc-100"
                  onClick={handleSignOut}
                  role="menuitem"
                >
                  <svg
                    className="h-4 w-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden="true"
                  >
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
        <header className="flex h-14 items-center border-b border-zinc-800 bg-zinc-950/70 px-4 backdrop-blur-2xl lg:hidden">
          <Link href="/projects" aria-label="Testlyn home">
            <LogoPulse size={20} wordmark={false} />
          </Link>
          <span className="ml-2 text-sm font-semibold text-zinc-100">
            Testlyn
          </span>
        </header>

        <main className="flex-1 overflow-auto bg-[radial-gradient(circle_at_85%_8%,rgba(24,242,195,0.10),transparent_28rem)]">{children}</main>
      </div>
    </div>
  );
}
