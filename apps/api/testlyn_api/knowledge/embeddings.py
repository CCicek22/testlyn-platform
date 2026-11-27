"""Embedders for knowledge chunks.

``HashingEmbedder`` is a deterministic, offline, lexical stand-in: it hashes
word unigrams and bigrams into a fixed-width vector. It captures shared
vocabulary only, not meaning. Use it for tests and CI, not for quality
retrieval.

``OpenAICompatEmbedder`` calls an OpenAI-style ``POST {base_url}/embeddings``
endpoint (for example a self-hosted embedding server).
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import httpx

from testlyn_api.config import get_settings
from testlyn_api.models.knowledge import KNOWLEDGE_EMBEDDING_DIM

# Unicode word characters, so Cyrillic, CJK and accented text produce features.
_TOKEN_RE = re.compile(r"\w+")


class EmbeddingError(Exception):
    """Embedding call failed or returned unusable vectors."""


class Embedder(Protocol):
    model_name: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Signed feature hashing of casefolded word unigrams and bigrams, L2-normalised.

    Deterministic across processes (blake2b, not Python's salted ``hash``).
    Text with no word characters (punctuation only) hashes the whole text as one
    feature, so every input yields a non-zero, unit-length vector and stays
    findable by cosine search. That fallback is not a semantic signal.
    """

    def __init__(self, dim: int = KNOWLEDGE_EMBEDDING_DIM) -> None:
        self.dim = dim
        self.model_name = f"hashing-{dim}-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        folded = text.casefold()
        tokens = _TOKEN_RE.findall(folded)
        if tokens:
            features = tokens + [
                f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False)
            ]
        else:
            features = [folded.strip() or "<empty>"]
        vec = [0.0] * self.dim
        for feature in features:
            digest = int.from_bytes(
                hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest(), "big"
            )
            index = digest % self.dim
            sign = -1.0 if digest >> 63 else 1.0
            vec[index] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            return vec
        return [x / norm for x in vec]


class OpenAICompatEmbedder:
    """Client for an OpenAI-style ``/embeddings`` endpoint.

    Requests are batched. Every returned vector must have ``dim`` elements.
    ``transport`` exists so tests can inject ``httpx.MockTransport``.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        dim: int = KNOWLEDGE_EMBEDDING_DIM,
        timeout_s: float = 30.0,
        batch_size: int = 32,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self.model_name = model
        self.dim = dim
        self._url = base_url.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._batch_size = batch_size
        self._transport = transport

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with httpx.AsyncClient(
            timeout=self._timeout_s, transport=self._transport
        ) as client:
            for start in range(0, len(texts), self._batch_size):
                batch = texts[start : start + self._batch_size]
                out.extend(await self._post_batch(client, batch))
        return out

    async def _post_batch(
        self, client: httpx.AsyncClient, batch: list[str]
    ) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            response = await client.post(
                self._url,
                json={"model": self.model_name, "input": batch},
                headers=headers,
            )
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise EmbeddingError(
                f"embedding request failed: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 400:
            raise EmbeddingError(
                f"embedding endpoint returned HTTP {response.status_code}"
            )

        try:
            data = response.json()["data"]
            indices = [item["index"] for item in data]
            ordered = sorted(data, key=lambda item: item["index"])
            vectors = [[float(x) for x in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise EmbeddingError("embedding response is malformed") from exc

        if len(vectors) != len(batch):
            raise EmbeddingError(
                f"embedding response has {len(vectors)} vectors for {len(batch)} inputs"
            )
        try:
            indices_match = sorted(indices) == list(range(len(batch)))
        except TypeError:
            indices_match = False
        if not indices_match:
            raise EmbeddingError("embedding response indices do not match the batch")
        for vec in vectors:
            if len(vec) != self.dim:
                raise EmbeddingError(
                    f"embedding has dimension {len(vec)}, expected {self.dim}"
                )
            if not all(math.isfinite(x) for x in vec):
                raise EmbeddingError("embedding contains non-finite values")
        return vectors


def get_embedder() -> Embedder:
    """Build the embedder selected by ``KNOWLEDGE_EMBEDDING_PROVIDER``."""
    settings = get_settings()
    if settings.knowledge_embedding_provider == "openai_compat":
        return OpenAICompatEmbedder(
            base_url=settings.knowledge_embedding_base_url,
            model=settings.knowledge_embedding_model,
            api_key=settings.knowledge_embedding_api_key,
            timeout_s=settings.knowledge_embedding_timeout_s,
            batch_size=settings.knowledge_embedding_batch_size,
        )
    return HashingEmbedder()
