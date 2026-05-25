"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function OnboardingForm() {
  const router = useRouter();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => api.orgs.create({ name: name.trim() }),
    onSuccess: async () => {
      // Refresh membership state so the dashboard org-guard sees the new org
      // before we land on /projects (otherwise it bounces back to onboarding).
      await qc.invalidateQueries({ queryKey: ["me"] });
      router.replace("/projects");
    },
    onError: (err) => {
      setError(
        err instanceof Error ? err.message : "Failed to create organization"
      );
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    mutation.mutate();
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {error && (
        <div
          role="alert"
          className="rounded-md bg-alert/10 px-3 py-2 text-sm text-alert"
        >
          {error}
        </div>
      )}
      <div>
        <label
          htmlFor="org-name"
          className="mb-1 block text-sm font-medium text-zinc-300"
        >
          Organization name
        </label>
        <Input
          id="org-name"
          required
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Acme Inc."
          className="border-zinc-700 bg-zinc-800 text-zinc-100 placeholder:text-zinc-500"
        />
        <p className="mt-1 text-xs text-zinc-500">
          You can rename it later in settings.
        </p>
      </div>
      <Button
        type="submit"
        disabled={mutation.isPending || !name.trim()}
        className="w-full"
      >
        {mutation.isPending ? "Creating…" : "Create organization"}
      </Button>
    </form>
  );
}
