"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Hook that manages command palette open/close state and
 * registers the Cmd+K (macOS) / Ctrl+K (Windows/Linux) global shortcut.
 */
export function useCmdk() {
  const [open, setOpen] = useState(false);

  const toggle = useCallback(() => setOpen((o) => !o), []);
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        toggle();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle]);

  return { open, setOpen, toggle, close };
}
