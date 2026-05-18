"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuth } from "@/components/auth/auth-provider";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { MeResponse } from "@testlyn/shared";

export default function MembersPage() {
  const { user } = useAuth();

  const { data: me, isLoading: meLoading } = useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => api.me(),
    enabled: user != null,
    staleTime: 5 * 60_000,
  });

  const orgId = me?.memberships?.[0]?.org_id ?? null;

  const { data: org, isLoading: orgLoading } = useQuery({
    queryKey: ["org", orgId],
    queryFn: () => api.orgs.get(orgId!),
    enabled: orgId != null,
    staleTime: 5 * 60_000,
  });

  const loading = meLoading || (orgId != null && orgLoading);

  return (
    <Card className="border-zinc-800 bg-zinc-900">
      <CardHeader className="pb-4">
        <CardTitle className="text-base text-zinc-100">Members</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-4 w-full bg-zinc-800" />
            <Skeleton className="h-4 w-3/4 bg-zinc-800" />
          </div>
        ) : org != null ? (
          <div className="flex flex-col items-center gap-4 py-10 text-center">
            <svg
              className="h-10 w-10 text-zinc-600"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
            <div>
              <p className="text-sm font-medium text-zinc-300">
                Member management coming in Phase 2
              </p>
              <p className="mt-1 text-sm text-zinc-500">
                Invite team members and manage roles when this feature ships.
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-zinc-500">
            {me == null ? "Loading organisation…" : "No organisation available."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
