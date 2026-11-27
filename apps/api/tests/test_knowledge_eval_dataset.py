from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from testlyn_api.knowledge.evaluation.dataset import DatasetError, load_eval_set


def _doc(tag: str, words: int = 320) -> str:
    # Heading "# Doc <tag>" adds three words, so the document has exactly ``words``.
    body = " ".join(f"{tag}t{i:04d}" for i in range(words - 3))
    return f"# Doc {tag}\n\n{body}\n"


def _docs(n: int = 12, words: int = 320) -> dict[str, str]:
    return {f"doc{i:02d}": _doc(f"d{i:02d}", words) for i in range(1, n + 1)}


def _token(docs: dict[str, str], name: str, i: int) -> str:
    return f"d{int(name[3:]):02d}t{i:04d}"


def _queries(docs: dict[str, str], n: int = 40) -> list[dict[str, Any]]:
    """Valid records: kinds cycle, paraphrase avoids long shared words."""
    names = sorted(docs)
    out: list[dict[str, Any]] = []
    for i in range(n):
        name = names[i % len(names)]
        span = _token(docs, name, i)
        kind = ("paraphrase", "keyword", "mixed")[i % 3]
        if kind == "paraphrase":
            query = f"Which entry is number {i} in the list?"
        elif kind == "keyword":
            query = f"What does the token {span} refer to?"
        else:
            query = f"Explain the {span} entry in plain words."
        out.append(
            {
                "id": f"q{i:03d}",
                "query": query,
                "kind": kind,
                "relevant": [{"document": name, "answer_span": span}],
            }
        )
    return out


def _write(
    tmp_path: Path,
    docs: dict[str, str],
    queries: list[Any] | None,
    *,
    raw_lines: list[str] | None = None,
) -> tuple[Path, Path]:
    corpus = tmp_path / "corpus"
    corpus.mkdir(exist_ok=True)
    for name, text in docs.items():
        (corpus / f"{name}.md").write_text(text, encoding="utf-8")
    qpath = tmp_path / "queries.jsonl"
    if raw_lines is not None:
        qpath.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
    else:
        assert queries is not None
        qpath.write_text(
            "".join(json.dumps(q) + "\n" for q in queries), encoding="utf-8"
        )
    return corpus, qpath


def test_valid_set_loads_with_counts(tmp_path: Path) -> None:
    docs = _docs()
    corpus, qpath = _write(tmp_path, docs, _queries(docs))
    evals = load_eval_set(corpus, qpath)
    assert len(evals.documents) == 12
    assert len(evals.queries) == 40
    assert {q.kind for q in evals.queries} == {"paraphrase", "keyword", "mixed"}


def test_checked_in_set_is_valid() -> None:
    root = Path(__file__).resolve().parents[1] / "evals" / "knowledge"
    evals = load_eval_set(root / "corpus", root / "queries.jsonl")
    assert 12 <= len(evals.documents) <= 16
    assert 40 <= len(evals.queries) <= 60


def test_span_missing_from_document_fails(tmp_path: Path) -> None:
    docs = _docs()
    queries = _queries(docs)
    queries[0]["relevant"][0]["answer_span"] = "not in this document"
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="not found"):
        load_eval_set(corpus, qpath)


def test_span_found_twice_fails(tmp_path: Path) -> None:
    docs = _docs()
    docs["doc01"] = docs["doc01"] + "d01t0000 again\n"
    corpus, qpath = _write(tmp_path, docs, _queries(docs))
    with pytest.raises(DatasetError, match="exactly once"):
        load_eval_set(corpus, qpath)


def test_overlapping_occurrences_count_as_several(tmp_path: Path) -> None:
    docs = _docs()
    docs["doc01"] = "# Doc\n\nxaaax " + "filler " * 320 + "\n"
    queries = _queries(docs)
    queries[0]["relevant"][0] = {"document": "doc01", "answer_span": "aa"}
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="exactly once"):
        load_eval_set(corpus, qpath)


def test_span_crossing_chunk_boundary_is_unreachable(tmp_path: Path) -> None:
    docs = _docs()
    left = " ".join(f"lft{i:04d}" for i in range(150))
    right = " ".join(f"rgt{i:04d}" for i in range(150))
    docs["doc01"] = f"# Split\n\n{left}\n\n{right}\n"
    tail = left[-200:]
    head = right[:200]
    queries = _queries(docs)
    queries[0]["relevant"][0] = {
        "document": "doc01",
        "answer_span": f"{tail}\n\n{head}",
    }
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="no chunk"):
        load_eval_set(corpus, qpath)


@pytest.mark.parametrize("n_docs", [11, 17])
def test_document_count_bounds(tmp_path: Path, n_docs: int) -> None:
    docs = _docs(n_docs)
    corpus, qpath = _write(tmp_path, docs, _queries(docs))
    with pytest.raises(DatasetError, match="documents"):
        load_eval_set(corpus, qpath)


@pytest.mark.parametrize("words", [299, 1201])
def test_document_word_bounds(tmp_path: Path, words: int) -> None:
    docs = _docs(12, words)
    corpus, qpath = _write(tmp_path, docs, _queries(docs))
    with pytest.raises(DatasetError, match="words"):
        load_eval_set(corpus, qpath)


@pytest.mark.parametrize("n_queries", [39, 61])
def test_query_count_bounds(tmp_path: Path, n_queries: int) -> None:
    docs = _docs()
    corpus, qpath = _write(tmp_path, docs, _queries(docs, n_queries))
    with pytest.raises(DatasetError, match="queries"):
        load_eval_set(corpus, qpath)


def test_duplicate_query_id_fails(tmp_path: Path) -> None:
    docs = _docs()
    queries = _queries(docs)
    queries[1]["id"] = queries[0]["id"]
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="duplicate"):
        load_eval_set(corpus, qpath)


def test_invalid_kind_fails(tmp_path: Path) -> None:
    docs = _docs()
    queries = _queries(docs)
    queries[0]["kind"] = "semantic"
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="kind"):
        load_eval_set(corpus, qpath)


def test_unknown_document_fails(tmp_path: Path) -> None:
    docs = _docs()
    queries = _queries(docs)
    queries[0]["relevant"][0]["document"] = "doc99"
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="unknown document"):
        load_eval_set(corpus, qpath)


def test_empty_relevant_list_fails(tmp_path: Path) -> None:
    docs = _docs()
    queries = _queries(docs)
    queries[0]["relevant"] = []
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="relevant"):
        load_eval_set(corpus, qpath)


def test_paraphrase_sharing_a_long_word_fails(tmp_path: Path) -> None:
    docs = _docs()
    queries = _queries(docs)
    paraphrase = next(q for q in queries if q["kind"] == "paraphrase")
    paraphrase["query"] = (
        "Which entry explains " + paraphrase["relevant"][0]["answer_span"]
    )
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="paraphrase"):
        load_eval_set(corpus, qpath)


def test_keyword_without_shared_rare_token_fails(tmp_path: Path) -> None:
    docs = _docs()
    queries = _queries(docs)
    keyword = next(q for q in queries if q["kind"] == "keyword")
    keyword["query"] = "What does the refund policy say?"
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="keyword"):
        load_eval_set(corpus, qpath)


@pytest.mark.parametrize(
    "line",
    [
        '{"id": "q1", "query": "x", "kind": "mixed"',
        '["not", "an", "object"]',
        '{"id": "q1", "query": "x", "kind": "mixed", "relevant": [], "extra": 1}',
        '{"id": 7, "query": "x", "kind": "mixed", "relevant": []}',
    ],
)
def test_malformed_record_fails_with_line_number(tmp_path: Path, line: str) -> None:
    docs = _docs()
    corpus, qpath = _write(tmp_path, docs, None, raw_lines=[line])
    with pytest.raises(DatasetError, match="line 1"):
        load_eval_set(corpus, qpath)


def test_bool_is_not_accepted_as_string_or_int(tmp_path: Path) -> None:
    docs = _docs()
    queries = _queries(docs)
    queries[0]["id"] = True
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="line 1"):
        load_eval_set(corpus, qpath)


def test_identical_document_text_fails(tmp_path: Path) -> None:
    docs = _docs()
    docs["doc02"] = docs["doc01"]
    corpus, qpath = _write(tmp_path, docs, _queries(docs))
    with pytest.raises(DatasetError, match="identical"):
        load_eval_set(corpus, qpath)


def test_two_queries_sharing_a_document_span_fails(tmp_path: Path) -> None:
    docs = _docs()
    queries = _queries(docs)
    twin = dict(queries[0], id="q-twin")
    queries.append(twin)
    corpus, qpath = _write(tmp_path, docs, queries)
    with pytest.raises(DatasetError, match="share"):
        load_eval_set(corpus, qpath)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What Happens Here", set()),
        ("Use the Retry Policy", set()),
        ("set gate.db_pool_size", {"gate.db_pool_size"}),
        ("SpoolBacklogHigh fires", {"SpoolBacklogHigh"}),
        ("error 5042 raised", {"5042"}),
        ("the `retry` flag", {"retry"}),
    ],
)
def test_rare_tokens_need_identifier_shape(text: str, expected: set[str]) -> None:
    from testlyn_api.knowledge.evaluation.dataset import _rare_tokens

    assert _rare_tokens(text) == expected
