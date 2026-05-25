import type { Metadata } from "next";
import { OnboardingForm } from "./onboarding-form";

export const metadata: Metadata = { title: "Create your organization" };

export default function OnboardingPage() {
  return (
    <div className="w-full max-w-sm">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
          Create your organization
        </h1>
        <p className="mt-2 text-sm text-zinc-400">
          Organizations hold your projects, tests, and team. Name yours to get
          started.
        </p>
      </div>
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6 shadow-sm">
        <OnboardingForm />
      </div>
    </div>
  );
}
