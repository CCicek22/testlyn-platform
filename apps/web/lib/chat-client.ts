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

const CHAT_BASE_URL =
  process.env["NEXT_PUBLIC_CHAT_BASE_URL"] ??
  "https://chat.dev.testlyn.example.com";

export interface TokenEvent {
  readonly kind: "token";
  readonly text: string;
}

export interface ToolCallEvent {
  readonly kind: "tool_call";
  readonly tool: string;
  readonly args: Record<string, unknown>;
}

export interface ToolResultEvent {
  readonly kind: "tool_result";
  readonly tool: string;
  readonly ok: boolean;
  readonly resultPreview: string;
}

export interface AgentSwitchEvent {
  readonly kind: "agent_switch";
  readonly to: string;
}

export interface ErrorEvent {
  readonly kind: "error";
  readonly error: string;
}

export interface DoneEvent {
  readonly kind: "done";
  readonly sessionId: string;
}

export type ChatEvent =
  | TokenEvent
  | ToolCallEvent
  | ToolResultEvent
  | AgentSwitchEvent
  | ErrorEvent
  | DoneEvent;

export interface StreamChatOptions {
  message: string;
  sessionId: string | null;
  signal?: AbortSignal;
  onEvent: (event: ChatEvent) => void;
}

interface ParsedFrame {
  event: string | null;
  data: string;
}

function parseFrame(chunk: string): ParsedFrame | null {
  let event: string | null = null;
  const dataLines: string[] = [];
  for (const rawLine of chunk.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line === "" || line.startsWith(":")) continue;
    const colonIdx = line.indexOf(":");
    if (colonIdx === -1) continue;
    const field = line.slice(0, colonIdx);
    const value = line.slice(colonIdx + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

function frameToEvent(frame: ParsedFrame): ChatEvent | null {
  let payload: unknown;
  try {
    payload = JSON.parse(frame.data);
  } catch {
    return null;
  }
  if (typeof payload !== "object" || payload === null) return null;
  const obj = payload as Record<string, unknown>;

  switch (frame.event) {
    case "token": {
      const text = typeof obj["text"] === "string" ? obj["text"] : "";
      return { kind: "token", text };
    }
    case "tool_call": {
      const tool = typeof obj["tool"] === "string" ? obj["tool"] : "unknown";
      const args =
        typeof obj["args"] === "object" && obj["args"] !== null
          ? (obj["args"] as Record<string, unknown>)
          : {};
      return { kind: "tool_call", tool, args };
    }
    case "tool_result": {
      const tool = typeof obj["tool"] === "string" ? obj["tool"] : "unknown";
      const ok = obj["ok"] === true;
      const resultPreview =
        typeof obj["result_preview"] === "string" ? obj["result_preview"] : "";
      return { kind: "tool_result", tool, ok, resultPreview };
    }
    case "agent_switch": {
      const to = typeof obj["to"] === "string" ? obj["to"] : "coordinator";
      return { kind: "agent_switch", to };
    }
    case "error": {
      const errMsg =
        typeof obj["error"] === "string" ? obj["error"] : "stream error";
      return { kind: "error", error: errMsg };
    }
    case "done": {
      const sessionId =
        typeof obj["session_id"] === "string" ? obj["session_id"] : "";
      return { kind: "done", sessionId };
    }
    default:
      return null;
  }
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

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const frame = parseFrame(chunk);
        if (!frame) continue;
        const evt = frameToEvent(frame);
        if (evt) onEvent(evt);
        if (evt?.kind === "done") return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
