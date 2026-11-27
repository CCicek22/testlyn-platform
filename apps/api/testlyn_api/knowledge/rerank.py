"""Optional reranker protocol. Concrete clients live alongside it."""

from __future__ import annotations

from typing import Protocol


class RerankError(Exception):
    """Reranker call failed or returned unusable scores."""


class Reranker(Protocol):
    async def rerank(
        self, query: str, documents: list[str], *, top_n: int
    ) -> list[tuple[int, float]]: ...
