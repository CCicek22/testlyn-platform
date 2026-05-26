"use client";

import { ToolCallBadge } from "./tool-call-badge";
import { AgentSwitchBadge } from "./agent-switch-badge";
import { cn } from "@/lib/utils";

export type BubbleSegment =
  | { kind: "text"; text: string }
  | { kind: "tool"; id: string; tool: string; ok?: boolean; resultPreview?: string }
  | { kind: "agent"; id: string; to: string };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  segments: BubbleSegment[];
  /** Streaming = assistant message currently receiving tokens. */
  streaming?: boolean;
}

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-[#031111]"
            : "border border-zinc-800 bg-zinc-900 text-zinc-100"
        )}
      >
        {message.segments.map((seg, i) => {
          if (seg.kind === "text") {
            return (
              <span key={`t-${i}`} className="whitespace-pre-wrap">
                {seg.text}
              </span>
            );
          }
          if (seg.kind === "tool") {
            return (
              <ToolCallBadge
                key={seg.id}
                tool={seg.tool}
                ok={seg.ok}
                resultPreview={seg.resultPreview}
              />
            );
          }
          return <AgentSwitchBadge key={seg.id} to={seg.to} />;
        })}
        {message.streaming && (
          <span
            className="ml-0.5 inline-block h-3 w-1.5 animate-pulse bg-zinc-400 align-middle"
            aria-hidden="true"
          />
        )}
      </div>
    </div>
  );
}
