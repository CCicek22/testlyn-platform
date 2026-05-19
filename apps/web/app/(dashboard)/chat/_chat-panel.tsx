"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/auth/auth-provider";
import {
  MessageBubble,
  type BubbleSegment,
  type ChatMessage,
} from "@/components/chat/message-bubble";
import { streamChat, type ChatEvent } from "@/lib/chat-client";

const SUGGESTIONS: readonly string[] = [
  "Start a load test against acme.com",
  "Show me last 5 runs",
  "Invite a member",
];

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

/**
 * Reducer-ish helper: take the current segment list of the streaming assistant
 * bubble and merge in a new SSE event. Returns a *new* array (immutable).
 */
function appendEventToSegments(
  segments: readonly BubbleSegment[],
  event: ChatEvent
): BubbleSegment[] {
  if (event.kind === "token") {
    // Coalesce consecutive token chunks into the trailing text segment.
    const last = segments[segments.length - 1];
    if (last && last.kind === "text") {
      return [
        ...segments.slice(0, -1),
        { kind: "text", text: last.text + event.text },
      ];
    }
    return [...segments, { kind: "text", text: event.text }];
  }
  if (event.kind === "tool_call") {
    return [
      ...segments,
      {
        kind: "tool",
        id: `tool-${newId()}`,
        tool: event.tool,
      },
    ];
  }
  if (event.kind === "tool_result") {
    // Settle the most recent matching unsettled tool segment.
    let settled = false;
    const updated: BubbleSegment[] = segments
      .slice()
      .reverse()
      .map((seg) => {
        if (
          !settled &&
          seg.kind === "tool" &&
          seg.tool === event.tool &&
          seg.ok === undefined
        ) {
          settled = true;
          return {
            ...seg,
            ok: event.ok,
            resultPreview: event.resultPreview,
          };
        }
        return seg;
      })
      .reverse();
    if (settled) return updated;
    // No matching pending tool — append as standalone.
    return [
      ...segments,
      {
        kind: "tool",
        id: `tool-${newId()}`,
        tool: event.tool,
        ok: event.ok,
        resultPreview: event.resultPreview,
      },
    ];
  }
  if (event.kind === "agent_switch") {
    return [...segments, { kind: "agent", id: `agent-${newId()}`, to: event.to }];
  }
  // done events are handled by the caller, never reach here
  return [...segments];
}

export function ChatPanel() {
  const { user, loading } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [, setSessionId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string | null>(null);

  // Auto-scroll to bottom on new messages / streaming tokens.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // Abort any in-flight stream on unmount.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const handleSend = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || sending) return;

      const userMsg: ChatMessage = {
        id: `u-${newId()}`,
        role: "user",
        segments: [{ kind: "text", text }],
      };
      const assistantId = `a-${newId()}`;
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        segments: [],
        streaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInput("");
      setError(null);
      setSending(true);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await streamChat({
          message: text,
          sessionId: sessionIdRef.current,
          signal: controller.signal,
          onEvent: (event) => {
            if (event.kind === "error") {
              setError(event.error);
              return;
            }
            if (event.kind === "done") {
              const resolved = event.sessionId || sessionIdRef.current;
              sessionIdRef.current = resolved;
              setSessionId(resolved);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, streaming: false } : m
                )
              );
              return;
            }
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, segments: appendEventToSegments(m.segments, event) }
                  : m
              )
            );
          },
        });
      } catch (err) {
        if ((err as { name?: string }).name === "AbortError") return;
        const msg = err instanceof Error ? err.message : "stream failed";
        setError(msg);
      } finally {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, streaming: false } : m
          )
        );
        setSending(false);
      }
    },
    [sending]
  );

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Cmd/Ctrl+Enter = send; plain Enter = newline.
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void handleSend(input);
    }
  }

  const inputDisabled = sending || loading || !user;
  const empty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header strip */}
      <header className="flex h-14 flex-shrink-0 items-center border-b border-zinc-800 px-6">
        <h1 className="text-sm font-semibold text-zinc-100">
          Chat <span className="text-zinc-500">— Testlyn copilot</span>
        </h1>
      </header>

      {/* Scrollable message list */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-6 py-6"
        aria-live="polite"
      >
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {empty && !sending && (
            <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
              <p className="text-base text-zinc-300">
                Ask Testlyn anything about your tests.
              </p>
              <p className="text-sm text-zinc-500">
                The copilot can route you to load, functional, security, and
                six more product agents.
              </p>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void handleSend(s)}
                    className="rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-xs text-zinc-300 transition-colors hover:border-zinc-700 hover:bg-zinc-800 hover:text-zinc-100"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}

          {error && (
            <div
              role="alert"
              className="rounded-md border border-alert/40 bg-alert/10 px-3 py-2 text-sm text-alert"
            >
              {error}
            </div>
          )}
        </div>
      </div>

      {/* Sticky input */}
      <div className="flex-shrink-0 border-t border-zinc-800 bg-dark px-6 py-4">
        <form
          className="mx-auto flex max-w-3xl items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void handleSend(input);
          }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask the copilot… (⌘+Enter to send)"
            rows={2}
            disabled={inputDisabled}
            className="min-h-[44px] flex-1 resize-none rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-primary focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
            aria-label="Message"
          />
          <Button
            type="submit"
            disabled={inputDisabled || !input.trim()}
            className="h-[44px] gap-1.5"
          >
            <Send className="h-4 w-4" aria-hidden="true" />
            <span>{sending ? "Sending…" : "Send"}</span>
          </Button>
        </form>
      </div>
    </div>
  );
}
