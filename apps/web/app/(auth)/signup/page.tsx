import type { Metadata } from "next";
import { SignupForm } from "./signup-form";

export const metadata: Metadata = { title: "Create account" };

export default function SignupPage() {
  return (
    <div className="w-full max-w-sm">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900">
          Create your account
        </h1>
        <p className="mt-2 text-sm text-zinc-500">
          Free to start. No credit card required.
        </p>
      </div>
      <SignupForm />
      <p className="mt-6 text-center text-sm text-zinc-500">
        Already have an account?{" "}
        <a href="/login" className="text-primary hover:underline">
          Sign in
        </a>
      </p>
    </div>
  );
}
