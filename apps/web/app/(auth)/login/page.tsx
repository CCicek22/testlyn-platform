import type { Metadata } from "next";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <div className="w-full max-w-sm">
      <div className="mb-8 text-center">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900">
          Sign in to Testlyn
        </h1>
        <p className="mt-2 text-sm text-zinc-500">
          Welcome back. Let&apos;s ship with data.
        </p>
      </div>
      <LoginForm />
      <p className="mt-6 text-center text-sm text-zinc-500">
        No account?{" "}
        <a href="/signup" className="text-primary hover:underline">
          Sign up free
        </a>
      </p>
    </div>
  );
}
