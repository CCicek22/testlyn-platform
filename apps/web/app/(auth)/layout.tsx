import Link from "next/link";
import { LogoPulse } from "@/components/brand/logo-pulse";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-light">
      <header className="px-4 py-4 sm:px-6">
        <Link href="/" aria-label="Testlyn home">
          <LogoPulse size={24} />
        </Link>
      </header>
      <main className="flex flex-1 items-center justify-center px-4 py-12 sm:px-6">
        {children}
      </main>
    </div>
  );
}
