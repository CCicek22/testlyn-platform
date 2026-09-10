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
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof UnauthenticatedError) {
    return false;
  }
  return failureCount < 1;
}

/**
 * Bounded exponential backoff delay for retries to prevent retry storms.
 */
export function defaultRetryDelay(attemptIndex: number): number {
  return Math.min(1000 * 2 ** attemptIndex, 10_000);
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: shouldRetryQuery,
      retryDelay: defaultRetryDelay,
      refetchOnWindowFocus: false,
    },
  },
});
