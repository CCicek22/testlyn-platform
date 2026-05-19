"use client";

import { ArrowRight } from "lucide-react";
import { getProduct, isProduct } from "@/lib/products";

interface AgentSwitchBadgeProps {
  to: string;
}

/**
 * Inline pill shown when the coordinator hands off to a sub-agent.
 * Color = product accent if `to` matches a known product id, otherwise indigo.
 */
export function AgentSwitchBadge({ to }: AgentSwitchBadgeProps) {
  const accent = isProduct(to) ? getProduct(to).accent : "#3730A3";
  const label = isProduct(to) ? `${getProduct(to).label.toLowerCase()} agent` : `${to} agent`;

  return (
    <div
      className="my-2 inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs"
      style={{ borderColor: `${accent}66`, color: accent, backgroundColor: `${accent}14` }}
    >
      <ArrowRight className="h-3 w-3" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
