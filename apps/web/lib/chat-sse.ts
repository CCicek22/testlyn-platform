/**
 * chat-sse — pure SSE wire-format parsing for the /chat/stream coordinator.
 *
 * Kept separate from chat-client.ts (which pulls in firebase + fetch) so the
 * parsing helpers are unit-testable without initializing the Firebase SDK.
 *
 * Backend contract (frozen by team-lead):
 *   response: text/event-stream, frames:
 *     event: token         data: { "text": "..." }
 *     event: tool_call     data: { "tool": "...", "args": {...} }
 *     event: tool_result   data: { "tool": "...", "ok": bool, "result_preview": "..." }
 *     event: agent_switch  data: { "to": "..." }
 *     event: done          data: { "session_id": "..." }
 */

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

interface ParsedFrame {
  event: string | null;
  data: string;
}

/**
 * Split an SSE buffer into complete frame chunks plus the trailing remainder.
 *
 * Frames are delimited by a blank line. sse-starlette (FastAPI) uses CRLF
 * (`\r\n\r\n`); the WHATWG spec also allows LF (`\n\n`). Normalize CRLF→LF so a
 * single LF-based split handles both, otherwise an all-CRLF stream never splits
 * and no frames are parsed.
 */
export function splitFrames(buffer: string): { frames: string[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  return { frames: parts, rest };
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

/** Parse a single SSE frame chunk into a ChatEvent (null if not parseable). */
export function parseChatFrame(chunk: string): ChatEvent | null {
  const frame = parseFrame(chunk);
  if (!frame) return null;
  return frameToEvent(frame);
}
