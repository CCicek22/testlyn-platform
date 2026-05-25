"use client";

/**
 * chat-client — POST + SSE stream for the ADK-backed coordinator at /chat/stream.
 *
 * EventSource can't set Authorization headers, so we fetch() with the bearer
 * token and parse the wire format ourselves. Pattern mirrors lib/sse.ts.
 *
 * Backend contract (frozen by team-lead):
 *   POST <CHAT_BASE_URL>/chat/stream
 *   headers: Authorization: Bearer <firebase id token>
 *   body:   { "message": string, "session_id": string | null }
 *   response: text/event-stream, frames:
 *     event: token         data: { "text": "..." }
 *     event: tool_call     data: { "tool": "...", "args": {...} }
 *     event: tool_result   data: { "tool": "...", "ok": bool, "result_preview": "..." }
 *     event: agent_switch  data: { "to": "..." }
 *     event: done          data: { "session_id": "..." }
 */

import { getIdToken } from "@/lib/firebase";
import { parseChatFrame, splitFrames, type ChatEvent } from "@/lib/chat-sse";

const CHAT_BASE_URL =
  process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "https://api.dev.testlyn.example.com";

export type {
  ChatEvent,
  TokenEvent,
  ToolCallEvent,
  ToolResultEvent,
  AgentSwitchEvent,
  ErrorEvent,
  DoneEvent,
} from "@/lib/chat-sse";
export { parseChatFrame, splitFrames } from "@/lib/chat-sse";

export interface StreamChatOptions {
  message: string;
  sessionId: string | null;
  signal?: AbortSignal;
  onEvent: (event: ChatEvent) => void;
}

export async function streamChat(opts: StreamChatOptions): Promise<void> {
  const { message, sessionId, signal, onEvent } = opts;

  let token = await getIdToken();
  if (!token) throw new Error("unauthenticated");

  const fetchOpts = {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  };

  let res = await fetch(`${CHAT_BASE_URL}/chat/stream`, {
    ...fetchOpts,
    headers: { ...fetchOpts.headers, Authorization: `Bearer ${token}` },
  });

  if (res.status === 401) {
    const fresh = await getIdToken(true);
    if (!fresh) throw new Error("auth: no token after refresh");
    token = fresh;
    res = await fetch(`${CHAT_BASE_URL}/chat/stream`, {
      ...fetchOpts,
      headers: { ...fetchOpts.headers, Authorization: `Bearer ${token}` },
    });
  }

  if (!res.ok || !res.body) {
    throw new Error(`chat stream status ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const { frames, rest } = splitFrames(buffer);
      buffer = rest;
      for (const chunk of frames) {
        const evt = parseChatFrame(chunk);
        if (!evt) continue;
        onEvent(evt);
        if (evt.kind === "done") return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
