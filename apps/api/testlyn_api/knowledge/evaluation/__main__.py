"""CLI: ``uv run python -m testlyn_api.knowledge.evaluation``.

Runs against an existing, migrated, empty Postgres database with pgvector.
The run creates and removes its own org. See README "Evaluating retrieval".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from collections.abc import Sequence

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from testlyn_api.config import get_settings
from testlyn_api.knowledge.embeddings import (
    HashingEmbedder,
    OpenAICompatEmbedder,
)
from testlyn_api.knowledge.evaluation.dataset import DatasetError, load_eval_set
from testlyn_api.knowledge.evaluation.judge import VertexJudgeModel
from testlyn_api.knowledge.evaluation.report import render_markdown
from testlyn_api.knowledge.evaluation.runner import EvaluationRefused, run_evaluation
from testlyn_api.models.knowledge import KNOWLEDGE_EMBEDDING_DIM

API_DIR = Path(__file__).resolve().parents[3]
DEFAULT_CORPUS = API_DIR / "evals" / "knowledge" / "corpus"
DEFAULT_QUERIES = API_DIR / "evals" / "knowledge" / "queries.jsonl"


def _parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="testlyn_api.knowledge.evaluation")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("TEST_POSTGRES_URL", ""),
        help="asyncpg URL of an empty, migrated database (default: $TEST_POSTGRES_URL)",
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument(
        "--embedder", choices=("hashing", "openai-compat"), default="hashing"
    )
    parser.add_argument(
        "--embedding-base-url",
        default=settings.knowledge_embedding_base_url,
        help="openai-compat only; the API key is read from KNOWLEDGE_EMBEDDING_API_KEY",
    )
    parser.add_argument("--embedding-model", default=settings.knowledge_embedding_model)
    parser.add_argument(
        "--embedding-dim",
        type=int,
        default=KNOWLEDGE_EMBEDDING_DIM,
        help=f"must equal {KNOWLEDGE_EMBEDDING_DIM}, the width of the vector column",
    )
    parser.add_argument("--json-out", type=Path, help="write the full report as JSON")
    parser.add_argument(
        "--judge", action="store_true", help="grade passages with the judge model"
    )
    parser.add_argument(
        "--judge-model",
        default="",
        help="required with --judge, e.g. gemini-3.1-flash-lite",
    )
    return parser


def _build_embedder(args: argparse.Namespace) -> HashingEmbedder | OpenAICompatEmbedder:
    if args.embedder == "hashing":
        return HashingEmbedder()
    if not args.embedding_base_url:
        raise SystemExit("error: --embedder openai-compat needs --embedding-base-url")
    if args.embedding_dim != KNOWLEDGE_EMBEDDING_DIM:
        raise SystemExit(f"error: --embedding-dim must be {KNOWLEDGE_EMBEDDING_DIM}")
    return OpenAICompatEmbedder(
        base_url=args.embedding_base_url,
        model=args.embedding_model,
        api_key=get_settings().knowledge_embedding_api_key,
        dim=args.embedding_dim,
        timeout_s=get_settings().knowledge_embedding_timeout_s,
    )


def _build_judge(args: argparse.Namespace) -> VertexJudgeModel | None:
    if not args.judge:
        return None
    if not args.judge_model:
        raise SystemExit("error: --judge needs --judge-model")
    settings = get_settings()
    return VertexJudgeModel(
        project=settings.gcp_project_id,
        location=settings.vertex_ai_location,
        model_name=args.judge_model,
    )


async def _check_migrated(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        has = await conn.run_sync(
            lambda sync: inspect(sync).has_table("knowledge_documents")
        )
    if not has:
        raise SystemExit(
            "error: knowledge tables missing; run `alembic upgrade head` first"
        )


async def _run(args: argparse.Namespace) -> int:
    if not args.database_url:
        print("error: set --database-url or TEST_POSTGRES_URL", file=sys.stderr)
        return 2
    dataset = load_eval_set(args.corpus, args.queries)
    embedder = _build_embedder(args)
    judge = _build_judge(args)
    engine = create_async_engine(args.database_url, poolclass=NullPool)
    try:
        await _check_migrated(engine)
        if judge is not None:
            # Load the SDK outside any per-call deadline.
            await judge.prepare()
        report = await run_evaluation(
            engine, dataset=dataset, embedder=embedder, judge=judge
        )
    except EvaluationRefused as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print(render_markdown(report), end="")
    if args.json_out is not None:
        args.json_out.write_text(
            json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except DatasetError as exc:
        print(f"error: invalid eval set: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
