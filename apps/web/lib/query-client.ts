import { QueryClient } from "@tanstack/react-query";
import { UnauthenticatedError } from "@/lib/api-client";

/**
 * Redirect on signed-out state is owned by AuthProvider + DashboardShell
 * (which subscribe to onAuthStateChanged and replace to /login when the user
 * truly becomes null). Doing it here as well caused spurious logouts on page
 * navigation when a query fired before Firebase finished its IndexedDB
 * restore — getIdToken() now awaits authStateReady(), but we still don't
 * retry on auth failures so the UI surfaces them cleanly.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) =>
        error instanceof UnauthenticatedError ? false : failureCount < 1,
      refetchOnWindowFocus: false,
    },
  },
});
