"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { Command } from "cmdk";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";

import { overlayVariants, paletteVariants } from "@/lib/motion";
import { buildCommandIndex, type CommandItem } from "./command-index";
import { api } from "@/lib/api-client";
import { signOutUser } from "@/lib/firebase";
import { cn } from "@/lib/utils";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

// Group display names
const GROUP_LABELS: Record<string, string> = {
  navigate: "Navigation",
  products: "Products",
  runs: "Recent Runs",
  actions: "Actions",
  settings: "Settings",
};

// Ordered group rendering
const GROUP_ORDER = ["actions", "navigate", "products", "runs", "settings"] as const;

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const reduced = useReducedMotion();
  const inputRef = useRef<HTMLInputElement>(null);
  const [search, setSearch] = useState("");

  // Fetch recent runs when the palette is opened. `enabled: open` prevents the
  // call firing on every dashboard mount before GET /v1/runs is wired (R5-B2).
  // Once F2's route lands and the query succeeds, staleTime keeps it cached for
  // 30 s so subsequent opens feel instant.
  const { data: recentRuns = [] } = useQuery({
    queryKey: ["runs", "recent"],
    queryFn: () => api.runs.list("load", 20),
    staleTime: 30_000,
    enabled: open,
  });

  // Reset search when palette closes
  const handleClose = useCallback(() => {
    setSearch("");
    onClose();
  }, [onClose]);

  const signOut = useCallback(async () => {
    handleClose();
    await signOutUser();
    router.replace("/login");
  }, [handleClose, router]);

  const commands = useMemo(
    () => buildCommandIndex(recentRuns, signOut),
    [recentRuns, signOut]
  );

  // Group commands
  const grouped = useMemo(() => {
    const lower = search.toLowerCase();
    const filtered = lower
      ? commands.filter(
          (c) =>
            c.label.toLowerCase().includes(lower) ||
            c.keywords.some((k) => k.toLowerCase().includes(lower))
        )
      : commands;

    const map = new Map<string, CommandItem[]>();
    for (const item of filtered) {
      const list = map.get(item.group) ?? [];
      list.push(item);
      map.set(item.group, list);
    }
    return map;
  }, [commands, search]);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      // Allow AnimatePresence to mount first
      const t = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(t);
    }
  }, [open]);

  function select(item: CommandItem) {
    handleClose();
    if (item.action) {
      void item.action();
    } else if (item.href) {
      router.push(item.href);
    }
  }

  const content = (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      {/* Backdrop */}
      <motion.div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        variants={reduced ? undefined : overlayVariants}
        initial="hidden"
        animate="visible"
        exit="exit"
        onClick={handleClose}
      />

      {/* Panel */}
      <motion.div
        className="relative z-10 w-full max-w-lg overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900 shadow-2xl"
        variants={reduced ? undefined : paletteVariants}
        initial={reduced ? undefined : "hidden"}
        animate={reduced ? undefined : "visible"}
        exit={reduced ? undefined : "exit"}
      >
        <Command
          className="flex flex-col"
          shouldFilter={false} // we filter manually above
          loop
        >
          {/* Search input */}
          <div className="flex items-center gap-2.5 border-b border-zinc-700 px-3 py-3">
            <svg
              className="h-4 w-4 flex-shrink-0 text-zinc-500"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <Command.Input
              ref={inputRef}
              value={search}
              onValueChange={setSearch}
              placeholder="Search commands, products, runs…"
              className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-500 outline-none"
            />
            <kbd className="hidden rounded border border-zinc-700 px-1.5 py-0.5 text-[10px] text-zinc-500 sm:block">
              ESC
            </kbd>
          </div>

          {/* Results */}
          <Command.List className="max-h-[320px] overflow-y-auto overscroll-contain p-2">
            <Command.Empty className="py-6 text-center text-sm text-zinc-500">
              No results for &ldquo;{search}&rdquo;
            </Command.Empty>

            {GROUP_ORDER.map((group) => {
              const items = grouped.get(group);
              if (!items?.length) return null;

              return (
                <Command.Group
                  key={group}
                  heading={GROUP_LABELS[group]}
                  className="[&>[cmdk-group-heading]]:px-2 [&>[cmdk-group-heading]]:pb-1 [&>[cmdk-group-heading]]:pt-3 [&>[cmdk-group-heading]]:text-[10px] [&>[cmdk-group-heading]]:font-semibold [&>[cmdk-group-heading]]:uppercase [&>[cmdk-group-heading]]:tracking-wider [&>[cmdk-group-heading]]:text-zinc-500"
                >
                  {items.map((item) => (
                    <Command.Item
                      key={item.id}
                      value={item.id}
                      onSelect={() => select(item)}
                      className={cn(
                        "flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-2 text-sm text-zinc-300",
                        "aria-selected:bg-zinc-800 aria-selected:text-zinc-100"
                      )}
                    >
                      {item.accent && (
                        <span
                          className="h-2 w-2 flex-shrink-0 rounded-full"
                          style={{ backgroundColor: item.accent }}
                          aria-hidden="true"
                        />
                      )}
                      <span className="flex-1 truncate">{item.label}</span>
                      {item.subtitle && (
                        <span className="text-xs text-zinc-500">
                          {item.subtitle}
                        </span>
                      )}
                    </Command.Item>
                  ))}
                </Command.Group>
              );
            })}
          </Command.List>

          {/* Footer hint */}
          <div className="border-t border-zinc-800 px-3 py-2 text-[10px] text-zinc-600">
            <kbd className="rounded border border-zinc-700 px-1 py-0.5">↑↓</kbd>{" "}
            navigate &nbsp;
            <kbd className="rounded border border-zinc-700 px-1 py-0.5">↵</kbd>{" "}
            select &nbsp;
            <kbd className="rounded border border-zinc-700 px-1 py-0.5">ESC</kbd>{" "}
            close
          </div>
        </Command>
      </motion.div>
    </div>
  );

  return (
    <AnimatePresence>
      {open && content}
    </AnimatePresence>
  );
}
