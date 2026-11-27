"""Chunker: heading paths, atomic code fences, source offsets, overlap."""

from __future__ import annotations

import pytest
from testlyn_api.knowledge.chunking import chunk_markdown

RUNBOOK = """# Runbook

Intro paragraph about the service.

## Rollback

Steps to roll back a release.
Run the revert job and wait for green.

```bash
kubectl rollout undo deploy/api

echo done
```

## Restart

Restart the workers one at a time.
"""


def _assert_offsets(text: str, chunks: list) -> None:
    for chunk in chunks:
        assert text[chunk.char_start : chunk.char_end] == chunk.text


def test_heading_path_is_tracked_per_chunk() -> None:
    chunks = chunk_markdown(RUNBOOK, target_chars=10_000)
    headings = [c.heading for c in chunks]
    assert headings == ["Runbook", "Runbook > Rollback", "Runbook > Restart"]


def test_nested_heading_resets_on_shallower_level() -> None:
    text = "# A\n\nbody a\n\n## A1\n\nbody a1\n\n# B\n\nbody b\n"
    chunks = chunk_markdown(text, target_chars=10_000)
    assert [c.heading for c in chunks] == ["A", "A > A1", "B"]


def test_code_fence_stays_whole() -> None:
    chunks = chunk_markdown(RUNBOOK, target_chars=10_000)
    rollback = next(c for c in chunks if c.heading == "Runbook > Rollback")
    assert "```bash\nkubectl rollout undo deploy/api\n\necho done\n```" in rollback.text


def test_code_fence_not_split_when_it_fits_after_paragraph() -> None:
    chunks = chunk_markdown(RUNBOOK, target_chars=120, overlap_chars=20)
    for chunk in chunks:
        assert chunk.text.count("```") in (0, 2)


def test_oversized_code_block_is_split() -> None:
    body = "\n".join(f"line_{i:03d} = {i}" for i in range(200))
    text = f"# Code\n\n```python\n{body}\n```\n"
    chunks = chunk_markdown(text, target_chars=300)
    assert len(chunks) > 3
    assert all(len(c.text) <= 300 for c in chunks)
    _assert_offsets(text, chunks)


def test_offsets_reproduce_source_span() -> None:
    chunks = chunk_markdown(RUNBOOK, target_chars=80, overlap_chars=20)
    assert chunks
    _assert_offsets(RUNBOOK, chunks)


def test_offsets_reproduce_source_span_with_crlf() -> None:
    text = RUNBOOK.replace("\n", "\r\n")
    chunks = chunk_markdown(text, target_chars=90, overlap_chars=15)
    _assert_offsets(text, chunks)


def test_offsets_are_monotonic_and_ordinals_sequential() -> None:
    chunks = chunk_markdown(RUNBOOK, target_chars=80, overlap_chars=20)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    starts = [c.char_start for c in chunks]
    assert starts == sorted(starts)
    assert all(c.char_start < c.char_end for c in chunks)


def test_overlap_repeats_text_between_neighbours() -> None:
    words = " ".join(f"word{i}" for i in range(400))
    chunks = chunk_markdown(words, target_chars=200, overlap_chars=40)
    assert len(chunks) >= 3
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert nxt.char_start < prev.char_end, "neighbouring spans should overlap"
        assert nxt.char_start > prev.char_start, "chunks must make progress"


def test_overlap_starts_on_word_boundary() -> None:
    words = " ".join(f"alpha{i}" for i in range(300))
    chunks = chunk_markdown(words, target_chars=150, overlap_chars=30)
    for chunk in chunks[1:]:
        assert not chunk.text[0].isspace()
        assert chunk.text.split()[0].startswith("alpha")


def test_zero_overlap_produces_disjoint_spans() -> None:
    words = " ".join(f"w{i}" for i in range(300))
    chunks = chunk_markdown(words, target_chars=120, overlap_chars=0)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert prev.char_end <= nxt.char_start


def test_chunks_respect_target_size() -> None:
    paragraphs = "\n\n".join("para " * 50 for _ in range(20))
    chunks = chunk_markdown(paragraphs, target_chars=400, overlap_chars=0)
    assert all(len(c.text) <= 400 for c in chunks)


def test_plain_text_without_headings() -> None:
    text = "First paragraph.\n\nSecond paragraph.\n"
    chunks = chunk_markdown(text, target_chars=10_000)
    assert len(chunks) == 1
    assert chunks[0].heading is None
    assert chunks[0].text == "First paragraph.\n\nSecond paragraph."
    _assert_offsets(text, chunks)


def test_empty_and_whitespace_input_yields_no_chunks() -> None:
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n\t\n") == []


def test_heading_only_document_yields_no_chunks() -> None:
    assert chunk_markdown("# Only a heading\n") == []


def test_unclosed_fence_runs_to_end() -> None:
    text = "# Open\n\n```\nnever closed\n"
    chunks = chunk_markdown(text, target_chars=10_000)
    assert "never closed" in chunks[-1].text
    _assert_offsets(text, chunks)


def test_token_estimate_is_chars_over_four() -> None:
    chunks = chunk_markdown("abcdefgh", target_chars=100, overlap_chars=0)
    assert chunks[0].token_estimate == 2


def test_deterministic() -> None:
    first = chunk_markdown(RUNBOOK, target_chars=80, overlap_chars=20)
    second = chunk_markdown(RUNBOOK, target_chars=80, overlap_chars=20)
    assert first == second


@pytest.mark.parametrize(("target", "overlap"), [(0, 0), (100, 100), (100, -1)])
def test_invalid_sizes_rejected(target: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_markdown("text", target_chars=target, overlap_chars=overlap)
