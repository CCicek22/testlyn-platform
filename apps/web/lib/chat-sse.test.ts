import { describe, it, expect } from "vitest";
import { splitFrames, parseChatFrame } from "./chat-sse";

describe("splitFrames", () => {
  it("splits a CRLF-delimited SSE buffer (sse-starlette wire format)", () => {
    const buffer =
      'event: token\r\ndata: {"text":"hi"}\r\n\r\n' +
      'event: done\r\ndata: {"session_id":"x"}\r\n\r\n';
    const { frames, rest } = splitFrames(buffer);
    expect(frames).toHaveLength(2);
    expect(rest).toBe("");
  });

  it("splits an LF-delimited SSE buffer (WHATWG format)", () => {
    const buffer =
      'event: token\ndata: {"text":"hi"}\n\n' +
      'event: done\ndata: {"session_id":"x"}\n\n';
    const { frames } = splitFrames(buffer);
    expect(frames).toHaveLength(2);
  });

  it("keeps an incomplete trailing frame as the remainder", () => {
    const buffer = 'event: token\r\ndata: {"text":"hi"}\r\n\r\nevent: token\r\ndata: ';
    const { frames, rest } = splitFrames(buffer);
    expect(frames).toHaveLength(1);
    expect(rest).toBe("event: token\ndata: ");
  });
});

describe("parseChatFrame over CRLF frames", () => {
  it("parses token + done events from a CRLF stream", () => {
    const buffer =
      'event: token\r\ndata: {"text":"hi"}\r\n\r\n' +
      'event: done\r\ndata: {"session_id":"x"}\r\n\r\n';
    const { frames } = splitFrames(buffer);
    const events = frames.map(parseChatFrame);

    expect(events[0]).toEqual({ kind: "token", text: "hi" });
    expect(events[1]).toEqual({ kind: "done", sessionId: "x" });
  });
});
