"""Load and validate the synthetic knowledge evaluation set.

Corpus: ``corpus/<doc_id>.md`` files. Queries: a JSONL file where each record is
``{"id", "query", "kind", "relevant": [{"document", "answer_span"}]}``.

A retrieved chunk is relevant to a gold entry when it comes from that document
and its text contains ``answer_span``. Validation enforces that the span occurs
exactly once in its document (overlapping occurrences included) and lies wholly
inside at least one chunk, so every gold entry is reachable by search.

Every file, line and record is size-bounded before parsing. The set is checked
as a whole, and any violation raises ``DatasetError`` with the query id or line
number.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testlyn_api.knowledge.chunking import chunk_markdown

KINDS = frozenset({"paraphrase", "keyword", "mixed"})

MIN_DOCUMENTS = 12
MAX_DOCUMENTS = 16
MIN_WORDS = 300
MAX_WORDS = 1200
MIN_QUERIES = 40
MAX_QUERIES = 60
MIN_PER_KIND = 10
MAX_RELEVANT = 10

MAX_FILE_BYTES = 256_000
MAX_LINE_BYTES = 8_000
MAX_QUERY_CHARS = 500
MAX_ID_CHARS = 64
PARAPHRASE_MIN_WORD = 6
RARE_TOKEN_MIN = 4

RECORD_KEYS = frozenset({"id", "query", "kind", "relevant"})
RELEVANT_KEYS = frozenset({"document", "answer_span"})

_WORD_RE = re.compile(r"\w+")
# One character class under a star: linear on any input.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*")


class DatasetError(ValueError):
    """Eval set is malformed."""


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    text: str
    word_count: int


@dataclass(frozen=True)
class RelevantSpan:
    document: str
    answer_span: str


@dataclass(frozen=True)
class Query:
    id: str
    query: str
    kind: str
    relevant: tuple[RelevantSpan, ...]


@dataclass(frozen=True)
class EvalSet:
    documents: tuple[Document, ...]
    queries: tuple[Query, ...]


def load_documents(corpus_dir: Path) -> list[Document]:
    if not corpus_dir.is_dir():
        raise DatasetError(f"corpus directory not found: {corpus_dir}")
    documents: list[Document] = []
    for path in sorted(corpus_dir.glob("*.md")):
        if path.stat().st_size > MAX_FILE_BYTES:
            raise DatasetError(f"document {path.name} exceeds {MAX_FILE_BYTES} bytes")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise DatasetError(f"document {path.name} is not UTF-8") from exc
        first = text.split("\n", 1)[0]
        title = first[2:].strip() if first.startswith("# ") else path.stem
        documents.append(
            Document(
                doc_id=path.stem,
                title=title,
                text=text,
                word_count=len(text.split()),
            )
        )
    return documents


def load_queries(queries_path: Path) -> list[Query]:
    try:
        size = queries_path.stat().st_size
    except OSError as exc:
        raise DatasetError(f"queries file not readable: {queries_path}") from exc
    if size > MAX_FILE_BYTES:
        raise DatasetError(f"queries file exceeds {MAX_FILE_BYTES} bytes")
    try:
        raw = queries_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise DatasetError("queries file is not UTF-8") from exc

    queries: list[Query] = []
    for number, line in enumerate(raw.split("\n"), start=1):
        if not line.strip():
            continue
        if len(line) > MAX_LINE_BYTES:
            raise DatasetError(f"line {number}: record is too long")
        try:
            record = json.loads(line)
        except (ValueError, RecursionError) as exc:
            raise DatasetError(f"line {number}: invalid JSON") from exc
        queries.append(_parse_record(record, number))
    return queries


def _parse_record(record: Any, number: int) -> Query:
    if not isinstance(record, dict):
        raise DatasetError(f"line {number}: record must be a JSON object")
    if set(record) != RECORD_KEYS:
        raise DatasetError(f"line {number}: record keys must be {sorted(RECORD_KEYS)}")
    qid = record["id"]
    if type(qid) is not str or not qid or len(qid) > MAX_ID_CHARS:
        raise DatasetError(f"line {number}: id must be a non-empty string")
    text = record["query"]
    if type(text) is not str or not text.strip() or len(text) > MAX_QUERY_CHARS:
        raise DatasetError(f"line {number}: query must be non-empty text")
    kind = record["kind"]
    if type(kind) is not str or kind not in KINDS:
        raise DatasetError(f"line {number}: kind must be one of {sorted(KINDS)}")
    relevant_raw = record["relevant"]
    if (
        type(relevant_raw) is not list
        or not relevant_raw
        or len(relevant_raw) > MAX_RELEVANT
    ):
        raise DatasetError(f"line {number}: relevant must be a non-empty list")
    relevant: list[RelevantSpan] = []
    for entry in relevant_raw:
        if not isinstance(entry, dict) or set(entry) != RELEVANT_KEYS:
            raise DatasetError(
                f"line {number}: each relevant entry needs keys {sorted(RELEVANT_KEYS)}"
            )
        document = entry["document"]
        span = entry["answer_span"]
        if type(document) is not str or not document:
            raise DatasetError(f"line {number}: document must be a non-empty string")
        if type(span) is not str or not span:
            raise DatasetError(f"line {number}: answer_span must be a non-empty string")
        relevant.append(RelevantSpan(document=document, answer_span=span))
    return Query(id=qid, query=text, kind=kind, relevant=tuple(relevant))


def _count_occurrences(text: str, span: str) -> int:
    """Occurrences including overlapping ones, stopping early at two."""
    count = 0
    start = 0
    while count < 2:
        found = text.find(span, start)
        if found < 0:
            break
        count += 1
        start = found + 1
    return count


def _rare_tokens(text: str) -> set[str]:
    return {
        tok
        for tok in _TOKEN_RE.findall(text)
        if len(tok) >= RARE_TOKEN_MIN
        and any(c.isdigit() or c == "_" or c.isupper() for c in tok)
    }


def _long_words(text: str) -> set[str]:
    return {
        w for w in _WORD_RE.findall(text.casefold()) if len(w) >= PARAPHRASE_MIN_WORD
    }


def validate_eval_set(documents: list[Document], queries: list[Query]) -> EvalSet:
    if not MIN_DOCUMENTS <= len(documents) <= MAX_DOCUMENTS:
        raise DatasetError(
            f"expected {MIN_DOCUMENTS} to {MAX_DOCUMENTS} documents, found {len(documents)}"
        )
    for doc in documents:
        if not MIN_WORDS <= doc.word_count <= MAX_WORDS:
            raise DatasetError(
                f"document {doc.doc_id} has {doc.word_count} words, "
                f"expected {MIN_WORDS} to {MAX_WORDS}"
            )
    if not MIN_QUERIES <= len(queries) <= MAX_QUERIES:
        raise DatasetError(
            f"expected {MIN_QUERIES} to {MAX_QUERIES} queries, found {len(queries)}"
        )

    by_id = {doc.doc_id: doc for doc in documents}
    chunks = {
        doc.doc_id: [c.text for c in chunk_markdown(doc.text)] for doc in documents
    }
    seen_ids: set[str] = set()
    per_kind: dict[str, int] = {kind: 0 for kind in KINDS}

    for query in queries:
        if query.id in seen_ids:
            raise DatasetError(f"duplicate query id {query.id}")
        seen_ids.add(query.id)
        per_kind[query.kind] += 1
        for rel in query.relevant:
            if rel.document not in by_id:
                raise DatasetError(f"query {query.id}: unknown document {rel.document}")
            occurrences = _count_occurrences(by_id[rel.document].text, rel.answer_span)
            if occurrences == 0:
                raise DatasetError(
                    f"query {query.id}: answer_span not found in {rel.document}"
                )
            if occurrences > 1:
                raise DatasetError(
                    f"query {query.id}: answer_span must occur exactly once in "
                    f"{rel.document}"
                )
            if not any(rel.answer_span in chunk for chunk in chunks[rel.document]):
                raise DatasetError(
                    f"query {query.id}: answer_span is in no chunk of {rel.document}"
                )
            _check_kind(query, rel.answer_span)

    for kind, count in sorted(per_kind.items()):
        if count < MIN_PER_KIND:
            raise DatasetError(
                f"kind {kind} has {count} queries, expected at least {MIN_PER_KIND}"
            )

    return EvalSet(documents=tuple(documents), queries=tuple(queries))


def _check_kind(query: Query, span: str) -> None:
    if query.kind == "paraphrase":
        if _long_words(query.query) & _long_words(span):
            raise DatasetError(
                f"query {query.id}: paraphrase query shares a long word with its answer"
            )
    elif not _rare_tokens(query.query) & _rare_tokens(span):
        raise DatasetError(
            f"query {query.id}: {query.kind} query shares no rare token with its answer"
        )


def load_eval_set(corpus_dir: Path, queries_path: Path) -> EvalSet:
    """Load and validate the corpus and the query file together."""
    return validate_eval_set(load_documents(corpus_dir), load_queries(queries_path))
