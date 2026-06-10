"use client";

/**
 * useSSE<T> — authenticated SSE hook with auto-reconnect.
 *
 * EventSource cannot set custom headers, so we cannot use it for endpoints
 * that require `Authorization: Bearer <id_token>` (e.g. /v1/runs/:id/stream).
 * We use fetch() + a ReadableStream reader and parse the standard SSE wire
 * format (events separated by blank lines, fields prefixed with `data:` /
 * `event:`). On 401 we refresh the token via getIdToken() and retry once.
 *
 * Emits each parsed SSE `data:` line as type T.
 * On permanent error, stops reconnecting and calls onError.
 */

import { useEffect, useRef } from "react";
import { getIdToken } from "@/lib/firebase";

interface UseSSEOptions<T> {
  /** Called for each successfully parsed message. */
  onMessage: (data: T) => void;
  /** Called on errors — reconnect will be attempted unless reconnectDelayMs=0. */
  onError?: (err: unknown) => void;
  /** Called when the server sends `event: done` or closes cleanly. */
  onDone?: () => void;
  /** Reconnect delay in ms (default 2000). Set to 0 to disable auto-reconnect. */
  reconnectDelayMs?: number;
  /** Whether the hook should connect at all (default true). */
  enabled?: boolean;
}

interface SSEEvent {
  event: string | null;
  data: string;
}

/**
 * Parse an SSE event chunk (one or more `field: value` lines).
 * Returns null if the chunk has no `data:` field.
 */
function parseEventChunk(chunk: string): SSEEvent | null {
  let event: string | null = null;
  const dataLines: string[] = [];
  for (const rawLine of chunk.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line === "" || line.startsWith(":")) continue;
    const colonIdx = line.indexOf(":");
    if (colonIdx === -1) continue;
    const field = line.slice(0, colonIdx);
    // Per spec, a single space after the colon is stripped.
    const value = line.slice(colonIdx + 1).replace(/^ /, "");
    if (field === "event") {
      event = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

export function useSSE<T>(
  url: string | null,
  options: UseSSEOptions<T>
): void {
  const {
    onMessage,
    onError,
    onDone,
    reconnectDelayMs = 2000,
    enabled = true,
  } = options;

  // Stable refs so the effect only re-runs when url/enabled change.
  const onMessageRef = useRef(onMessage);
  const onErrorRef = useRef(onError);
  const onDoneRef = useRef(onDone);
  const reconnectDelayRef = useRef(reconnectDelayMs);

  useEffect(() => {
    onMessageRef.current = onMessage;
    onErrorRef.current = onError;
    onDoneRef.current = onDone;
    reconnectDelayRef.current = reconnectDelayMs;
  });

  useEffect(() => {
    if (!url || !enabled) return;

    let controller: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    async function readStream(): Promise<void> {
      if (stopped) return;

      controller = new AbortController();

      // Get token; on 401 we refresh once via a second getIdToken() call.
      let token = await getIdToken();
      if (!token) {
        stopped = true;
        onErrorRef.current?.(new Error("unauthenticated"));
        return;
      }

      let res: Response;
      try {
        res = await fetch(url!, {
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: "text/event-stream",
          },
          signal: controller.signal,
        });
      } catch (err) {
        if ((err as { name?: string }).name === "AbortError") return;
        onErrorRef.current?.(err);
        scheduleReconnect();
        return;
      }

      if (res.status === 401) {
        // Force-refresh the token + retry once. Without forceRefresh Firebase
        // returns the same cached (rejected) JWT and the retry is doomed.
        token = await getIdToken(true);
        if (!token) {
          stopped = true;
          onErrorRef.current?.(new Error("unauthenticated"));
          return;
        }
        try {
          res = await fetch(url!, {
            headers: {
              Authorization: `Bearer ${token}`,
              Accept: "text/event-stream",
            },
            signal: controller.signal,
          });
        } catch (err) {
          if ((err as { name?: string }).name === "AbortError") return;
          onErrorRef.current?.(err);
          scheduleReconnect();
          return;
        }
      }

      if (!res.ok || !res.body) {
        onErrorRef.current?.(new Error(`sse status ${res.status}`));
        scheduleReconnect();
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      try {
        while (!stopped) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE events are delimited by a blank line. Normalize CRLF→LF so the
          // LF split also handles sse-starlette's CRLF frames (defensive: this
          // endpoint emits LF today but may move to sse-starlette).
          buffer = buffer.replace(/\r\n/g, "\n");
          let sep: number;
          while ((sep = buffer.indexOf("\n\n")) !== -1) {
            const chunk = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);
            const evt = parseEventChunk(chunk);
            if (!evt) continue;
            if (evt.event === "done") {
              stopped = true;
              onDoneRef.current?.();
              return;
            }
            try {
              const parsed = JSON.parse(evt.data) as T;
              onMessageRef.current(parsed);
            } catch {
              // Ignore malformed JSON frames.
            }
          }
        }
      } catch (err) {
        if ((err as { name?: string }).name === "AbortError") return;
        onErrorRef.current?.(err);
        scheduleReconnect();
        return;
      }

      // Clean EOF — schedule reconnect unless disabled.
      if (!stopped) scheduleReconnect();
    }

    function scheduleReconnect(): void {
      if (stopped) return;
      if (reconnectDelayRef.current === 0) {
        stopped = true;
        return;
      }
      timer = setTimeout(() => {
        void readStream();
      }, reconnectDelayRef.current);
    }

    void readStream();

    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      controller?.abort();
    };
  }, [url, enabled]);
}
