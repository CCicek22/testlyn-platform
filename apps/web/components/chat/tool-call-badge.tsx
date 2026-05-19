"use client";

import { Wrench } from "lucide-react";
import { cn } from "@/lib/utils";

interface ToolCallBadgeProps {
  tool: string;
  ok?: boolean;
  resultPreview?: string;
}

export function ToolCallBadge({ tool, ok, resultPreview }: ToolCallBadgeProps) {
  const settled = ok !== undefined;
  const status = !settled
    ? "border-zinc-700 bg-zinc-800/60 text-zinc-300"
    : ok
      ? "border-success/40 bg-success/10 text-success"
      : "border-alert/40 bg-alert/10 text-alert";

  return (
    <div className="my-2 flex flex-col gap-1">
      <div
        className={cn(
          "inline-flex w-fit items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-xs",
          status
        )}
      >
        <Wrench className="h-3 w-3" aria-hidden="true" />
        <span>{tool}</span>
        {!settled && (
          <span className="ml-1 text-[10px] text-zinc-500">running…</span>
        )}
      </div>
      {resultPreview && (
        <pre className="max-h-32 overflow-auto rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 font-mono text-[11px] text-zinc-400">
          {resultPreview}
        </pre>
      )}
    </div>
  );
}
