"use client";

/**
 * useSSE<T> — EventSource hook with auto-reconnect.
 *
 * Emits each parsed SSE `data:` line as type T.
 * On permanent error, stops reconnecting and calls onError.
 */

import { useEffect, useRef } from "react";

interface UseSSEOptions<T> {
  /** Called for each successfully parsed message. */
  onMessage: (data: T) => void;
  /** Called on errors — reconnect will be attempted unless reconnectDelayMs=0. */
  onError?: (err: Event) => void;
  /** Called when the server sends `event: done` or closes cleanly. */
  onDone?: () => void;
  /** Reconnect delay in ms (default 2000). Set to 0 to disable auto-reconnect. */
  reconnectDelayMs?: number;
  /** Whether the hook should connect at all (default true). */
  enabled?: boolean;
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

  // Stable refs so effect only re-runs when url/enabled changes.
  // Ref assignment is deferred to a layout effect — assigning during render
  // breaks Strict Mode and React 19's render-purity check.
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

    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    function connect(): void {
      if (stopped) return;

      es = new EventSource(url!);

      es.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data as string) as T;
          onMessageRef.current(data);
        } catch {
          // Ignore malformed frames
        }
      };

      es.addEventListener("done", () => {
        es?.close();
        es = null;
        stopped = true;
        onDoneRef.current?.();
      });

      es.onerror = (evt) => {
        es?.close();
        es = null;

        if (reconnectDelayRef.current === 0) {
          stopped = true;
          onErrorRef.current?.(evt);
          return;
        }

        onErrorRef.current?.(evt);

        timer = setTimeout(() => {
          connect();
        }, reconnectDelayRef.current);
      };
    }

    connect();

    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      es?.close();
    };
  }, [url, enabled]);
}
