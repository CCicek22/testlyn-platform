"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuth } from "@/components/auth/auth-provider";
import { signOutUser } from "@/lib/firebase";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { MeResponse, Org } from "@testlyn/shared";

function FieldRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex flex-col gap-1 border-b border-zinc-800 py-3 first:pt-0 last:border-0 last:pb-0">
      <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</span>
      {value != null && value !== "" ? (
        <span className="text-sm text-zinc-100">{value}</span>
      ) : (
        <span className="text-sm italic text-zinc-500">—</span>
      )}
    </div>
  );
}

export default function AccountPage() {
  const { user } = useAuth();

  const { data: me, isLoading: meLoading } = useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => api.me(),
    enabled: user != null,
    staleTime: 5 * 60_000,
  });

  const orgId = me?.memberships?.[0]?.org_id ?? null;

  const { data: org, isLoading: orgLoading } = useQuery<Org>({
    queryKey: ["org", orgId],
    queryFn: () => api.orgs.get(orgId!),
    enabled: orgId != null,
    staleTime: 5 * 60_000,
  });

  async function handleSignOut() {
    await signOutUser();
    window.location.href = "/login";
  }

  const loading = meLoading || (orgId != null && orgLoading);

  return (
    <div className="flex flex-col gap-6">
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader className="pb-4">
          <CardTitle className="text-base text-zinc-100">Profile</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex flex-col gap-3">
              <Skeleton className="h-4 w-48 bg-zinc-800" />
              <Skeleton className="h-4 w-64 bg-zinc-800" />
              <Skeleton className="h-4 w-40 bg-zinc-800" />
            </div>
          ) : (
            <div>
              <FieldRow label="Email" value={me?.email} />
              <FieldRow label="Display name" value={me?.name} />
              <FieldRow label="Organisation" value={org?.name} />
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader className="pb-4">
          <CardTitle className="text-base text-zinc-100">Session</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-zinc-400">
            Sign out of your account on this device.
          </p>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => void handleSignOut()}
          >
            Sign out
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
