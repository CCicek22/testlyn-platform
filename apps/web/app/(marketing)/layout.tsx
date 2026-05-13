import Link from "next/link";
import { LogoPulse } from "@/components/brand/logo-pulse";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-light text-zinc-900">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b border-zinc-200 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <Link href="/" aria-label="Testlyn home">
            <LogoPulse size={24} />
          </Link>
          <nav className="hidden items-center gap-6 text-sm text-zinc-600 sm:flex">
            <Link href="/docs" className="hover:text-zinc-900 transition-colors">
              Docs
            </Link>
            <Link href="/blog" className="hover:text-zinc-900 transition-colors">
              Blog
            </Link>
            <Link href="/changelog" className="hover:text-zinc-900 transition-colors">
              Changelog
            </Link>
            <Link href="/pricing" className="hover:text-zinc-900 transition-colors">
              Pricing
            </Link>
            <Link href="/status" className="hover:text-zinc-900 transition-colors">
              Status
            </Link>
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="text-sm text-zinc-600 hover:text-zinc-900 transition-colors"
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-600 transition-colors"
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main>{children}</main>

      <footer className="border-t border-zinc-200 py-10">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <LogoPulse size={20} />
            <p className="text-xs text-zinc-400">
              &copy; {new Date().getFullYear()} Testlyn. Built for engineers who ship with data.
            </p>
            <nav className="flex gap-4 text-xs text-zinc-400">
              <Link href="/docs" className="hover:text-zinc-600">Docs</Link>
              <Link href="/blog" className="hover:text-zinc-600">Blog</Link>
              <Link href="/pricing" className="hover:text-zinc-600">Pricing</Link>
              <Link href="/changelog" className="hover:text-zinc-600">Changelog</Link>
              <Link href="/status" className="hover:text-zinc-600">Status</Link>
            </nav>
          </div>
        </div>
      </footer>
    </div>
  );
}
