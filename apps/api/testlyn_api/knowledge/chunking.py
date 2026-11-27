"""Markdown-aware chunker for knowledge documents.

Pure function: no I/O, deterministic. Every chunk is a span of the original
text, so ``original[chunk.char_start:chunk.char_end] == chunk.text`` always
holds. Spans of neighbouring chunks may overlap (see ``overlap_chars``).

Rules
-----
- Headings (ATX ``#`` style) start a new section. ``heading`` on a chunk is the
  heading path of its section, e.g. ``"Runbook > Rollback"``.
- Paragraphs are separated by blank lines and packed into chunks up to
  ``target_chars``.
- Fenced code blocks (``` or ~~~) are atomic: never split, unless the block
  alone exceeds ``target_chars``.
- Overlap is only carried between consecutive chunks of one section, and only
  when the previous chunk ends in a paragraph (never a code block).
- Plain text (no headings) works: the whole input is one section.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_TARGET_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 150
MAX_HEADING_CHARS = 300

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(\S.*?)[ \t]*$")


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    heading: str | None
    text: str
    char_start: int
    char_end: int
    # chars/4 heuristic. Not a real tokenizer count.
    token_estimate: int


@dataclass(slots=True)
class _Segment:
    start: int
    end: int
    kind: str  # "heading" | "code" | "para"
    path: str | None
    section: int


@dataclass(slots=True)
class _Span:
    start: int
    end: int
    path: str | None
    section: int
    last_kind: str
    has_content: bool


def chunk_markdown(
    text: str,
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[Chunk]:
    """Split ``text`` into heading-aware chunks with source offsets."""
    if target_chars < 1:
        raise ValueError("target_chars must be >= 1")
    if not 0 <= overlap_chars < target_chars:
        raise ValueError("overlap_chars must be >= 0 and < target_chars")

    # Pieces leave room for the overlap, so an overlap always fits in a chunk.
    piece_limit = target_chars - overlap_chars
    units: list[_Segment] = []
    for seg in _segments(text):
        units.extend(_split_oversized(text, seg, piece_limit))

    spans = _pack(text, units, target_chars, overlap_chars)

    chunks: list[Chunk] = []
    for span in spans:
        s, e = _trim(text, span.start, span.end)
        if s >= e:
            continue
        body = text[s:e]
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                heading=_clip_heading(span.path),
                text=body,
                char_start=s,
                char_end=e,
                token_estimate=(len(body) + 3) // 4,
            )
        )
    return chunks


def _segments(text: str) -> list[_Segment]:
    segs: list[_Segment] = []
    titles: list[tuple[int, str]] = []
    section = 0
    path: str | None = None

    para_start: int | None = None
    para_end = 0
    fence: tuple[str, int] | None = None
    fence_start = 0

    def flush_para() -> None:
        nonlocal para_start
        if para_start is not None:
            segs.append(_Segment(para_start, para_end, "para", path, section))
            para_start = None

    pos = 0
    for line in text.splitlines(keepends=True):
        start = pos
        pos += len(line)

        if fence is not None:
            stripped = line.strip()
            if stripped and set(stripped) <= {fence[0]} and len(stripped) >= fence[1]:
                segs.append(_Segment(fence_start, pos, "code", path, section))
                fence = None
            continue

        if not line.strip():
            flush_para()
            continue

        fence_match = _FENCE_RE.match(line)
        if fence_match:
            flush_para()
            marker = fence_match.group(1)
            fence = (marker[0], len(marker))
            fence_start = start
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush_para()
            level = len(heading_match.group(1))
            while titles and titles[-1][0] >= level:
                titles.pop()
            titles.append((level, heading_match.group(2)))
            path = " > ".join(title for _, title in titles)
            section += 1
            segs.append(_Segment(start, pos, "heading", path, section))
            continue

        if para_start is None:
            para_start = start
        para_end = pos

    if fence is not None:
        segs.append(_Segment(fence_start, len(text), "code", path, section))
    flush_para()
    return segs


def _split_oversized(text: str, seg: _Segment, limit: int) -> list[_Segment]:
    """Break a segment larger than ``limit`` into line-packed pieces."""
    if seg.end - seg.start <= limit:
        return [seg]

    pieces: list[_Segment] = []
    cursor = seg.start
    while cursor < seg.end:
        end = min(cursor + limit, seg.end)
        if end < seg.end:
            # Break after the last whitespace in the window, so words stay whole.
            for k in range(end - 1, cursor, -1):
                if text[k].isspace():
                    end = k + 1
                    break
        pieces.append(_Segment(cursor, end, seg.kind, seg.path, seg.section))
        cursor = end
    return pieces


def _pack(
    text: str,
    units: list[_Segment],
    target: int,
    overlap: int,
) -> list[_Span]:
    out: list[_Span] = []
    cur: _Span | None = None

    for unit in units:
        if unit.kind == "heading":
            if cur is not None and cur.has_content:
                out.append(cur)
                cur = None
            if cur is None:
                cur = _Span(
                    unit.start, unit.end, unit.path, unit.section, "heading", False
                )
            else:
                # Consecutive headings with no body between: merge, keep the deepest path.
                cur.end = unit.end
                cur.path = unit.path
                cur.section = unit.section
            continue

        if cur is None:
            cur = _Span(unit.start, unit.end, unit.path, unit.section, unit.kind, True)
            continue

        if unit.end - cur.start <= target:
            cur.end = unit.end
            cur.path = unit.path
            cur.last_kind = unit.kind
            cur.has_content = True
            continue

        prev = cur
        out.append(prev)
        start = unit.start
        if prev.last_kind == "para":
            overlap_start = _overlap_start(text, prev, overlap)
            if overlap_start is not None and unit.end - overlap_start <= target:
                start = overlap_start
        cur = _Span(start, unit.end, unit.path, unit.section, unit.kind, True)

    if cur is not None and cur.has_content:
        out.append(cur)
    return out


def _overlap_start(text: str, prev: _Span, overlap: int) -> int | None:
    """Start of the tail of ``prev`` to repeat, snapped to a word boundary."""
    if overlap <= 0:
        return None
    window_start = prev.end - overlap
    if window_start <= prev.start:
        return None
    for k in range(window_start, prev.end):
        if text[k - 1].isspace() and not text[k].isspace():
            return k
    return None


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _clip_heading(path: str | None) -> str | None:
    if path is None:
        return None
    return path[:MAX_HEADING_CHARS]
