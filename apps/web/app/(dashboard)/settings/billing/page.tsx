"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAuth } from "@/components/auth/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { MeResponse } from "@testlyn/shared";

const PLAN_LABELS: Record<string, string> = {
  free: "Free",
  hobby: "Hobby",
  pro: "Pro",
  business: "Business",
  enterprise: "Enterprise",
};

export default function BillingPage() {
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
  const plan = org?.plan ?? "free";
  const planLabel = PLAN_LABELS[plan] ?? plan;

  return (
    <div className="flex flex-col gap-6">
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader className="pb-4">
          <CardTitle className="text-base text-zinc-100">Current plan</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-5 w-24 bg-zinc-800" />
          ) : (
            <span className="inline-flex items-center rounded-full bg-primary/10 px-3 py-1 text-sm font-semibold text-primary">
              {planLabel}
            </span>
          )}
        </CardContent>
      </Card>

      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader className="pb-4">
          <CardTitle className="text-base text-zinc-100">Subscription</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-zinc-400">
            Upgrade, downgrade, or manage payment methods through the Stripe customer portal.
          </p>
          <Button
            size="sm"
            disabled
            title="Stripe billing portal available in Phase 2"
          >
            Manage subscription in Stripe
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
