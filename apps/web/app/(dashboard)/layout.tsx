// Server-side wrapper for the (dashboard) route group.
//
// The shell uses client-only navigation hooks (useSearchParams, usePathname)
// and live data fetching, so the segment must be fully dynamic — Next would
// otherwise refuse to prerender during `next build`. Keeping the shell as a
// client component while letting this server layout own the route-segment
// config gives us both behaviours.

import DashboardShell from "./_dashboard-shell";

export const dynamic = "force-dynamic";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
