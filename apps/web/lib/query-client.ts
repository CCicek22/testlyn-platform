import { QueryCache, QueryClient } from "@tanstack/react-query";
import { UnauthenticatedError } from "@/lib/api-client";

/**
 * R5-C4: Global UnauthenticatedError handler.
 * When any query throws UnauthenticatedError (null token, not in dev-bypass),
 * redirect to /login. React Query v5 requires onError on QueryCache directly
 * rather than defaultOptions (the v4 global callback was removed).
 */
export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError(error) {
      if (error instanceof UnauthenticatedError) {
        // Use replace so the user can't back-navigate into the protected page.
        window.location.replace("/login");
      }
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Do not retry on auth failures — redirect immediately.
      retry: (failureCount, error) =>
        error instanceof UnauthenticatedError ? false : failureCount < 1,
      refetchOnWindowFocus: false,
    },
  },
});
