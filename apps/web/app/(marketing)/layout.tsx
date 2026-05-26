import Link from "next/link";
import { LogoPulse } from "@/components/brand/logo-pulse";
import { MarketingThemeToggle } from "@/components/theme/marketing-theme-toggle";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-light text-[var(--glass-ink)] transition-colors dark:bg-dark">
      {/* Nav */}
      <header className="sticky top-0 z-50 border-b border-[var(--glass-border)] bg-[var(--glass-panel)] backdrop-blur-2xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <Link href="/" aria-label="Testlyn home">
            <LogoPulse size={24} />
          </Link>
          <nav className="hidden items-center gap-6 text-sm text-[var(--glass-muted)] sm:flex">
            <Link href="/docs" className="transition-colors hover:text-primary">
              Docs
            </Link>
            <Link href="/blog" className="transition-colors hover:text-primary">
              Blog
            </Link>
            <Link href="/changelog" className="transition-colors hover:text-primary">
              Changelog
            </Link>
            <Link href="/pricing" className="transition-colors hover:text-primary">
              Pricing
            </Link>
            <Link href="/status" className="transition-colors hover:text-primary">
              Status
            </Link>
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="text-sm text-[var(--glass-muted)] transition-colors hover:text-primary"
            >
              Sign in
            </Link>
            <MarketingThemeToggle />
            <Link
              href="/signup"
              className="trace-glow rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-[#031111] transition-all hover:-translate-y-0.5 hover:bg-primary-100"
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main>{children}</main>

      <footer className="border-t border-[var(--glass-border)] bg-[var(--glass-panel)] py-10 backdrop-blur-xl">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <LogoPulse size={20} />
            <p className="text-xs text-[var(--glass-faint)]">
              &copy; {new Date().getFullYear()} Testlyn. Built for engineers who ship with data.
            </p>
            <nav className="flex gap-4 text-xs text-[var(--glass-faint)]">
              <Link href="/docs" className="hover:text-primary">Docs</Link>
              <Link href="/blog" className="hover:text-primary">Blog</Link>
              <Link href="/pricing" className="hover:text-primary">Pricing</Link>
              <Link href="/changelog" className="hover:text-primary">Changelog</Link>
              <Link href="/status" className="hover:text-primary">Status</Link>
            </nav>
          </div>
        </div>
      </footer>
    </div>
  );
}
