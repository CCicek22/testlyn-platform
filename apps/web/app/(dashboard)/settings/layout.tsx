import { SettingsNav } from "./_settings-nav";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-100">
          Settings
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          Manage your account, API keys, billing, and team.
        </p>
      </div>

      <div className="flex gap-8">
        {/* Left sub-nav */}
        <aside className="w-44 flex-shrink-0">
          <SettingsNav />
        </aside>

        {/* Page content */}
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
