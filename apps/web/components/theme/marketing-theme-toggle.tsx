"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

const THEMES = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

const emptySubscribe = () => () => {};

export function MarketingThemeToggle() {
  const { theme, setTheme } = useTheme();
  // Avoid hydration mismatch: render the placeholder ("system") on the server
  // and first client paint, then the resolved theme once mounted. Derived via
  // useSyncExternalStore so we never call setState inside an effect.
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  const currentTheme = mounted ? theme ?? "system" : "system";

  return (
    <div
      className="flex rounded-full border border-[var(--glass-border)] bg-[var(--glass-panel)] p-1 backdrop-blur-xl"
      aria-label="Theme"
    >
      {THEMES.map((item) => {
        const Icon = item.icon;
        const active = currentTheme === item.value;

        return (
          <button
            key={item.value}
            type="button"
            onClick={() => setTheme(item.value)}
            className={[
              "flex h-7 w-7 items-center justify-center rounded-full transition-all",
              active
                ? "bg-primary text-[#031111] shadow-[0_0_18px_rgba(24,242,195,0.25)]"
                : "text-[var(--glass-muted)] hover:bg-primary/10 hover:text-primary",
            ].join(" ")}
            aria-label={`Use ${item.label} theme`}
            aria-pressed={active}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}
