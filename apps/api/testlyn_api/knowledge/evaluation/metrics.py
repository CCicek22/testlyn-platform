"""Ranking metrics for retrieval evaluation (binary relevance).

Inputs
------
``ranking``
    Result identifiers, best first (for example chunk ids from one search).
``matches``
    Maps a result identifier to the set of gold ids it satisfies. A result
    that is missing from the mapping, or maps to an empty set, is not relevant.
``gold``
    All gold ids of the query. Recall is the share of these that the top k
    results cover.

Edge cases
----------
- ``gold`` empty: every metric raises ``ValueError``. The metric is undefined,
  and returning 0.0 would silently drag down averages.
- ``k < 1``: ``ValueError``.
- ``k`` larger than the ranking: the whole ranking is used.
- Repeated result identifiers: only the first occurrence counts and takes a
  rank. Repeats do not push later results down.
- nDCG gain: a result earns gain 1 when it covers at least one gold id that no
  higher-ranked result covered. The ideal DCG assumes one gain per gold id, so
  nDCG stays in [0, 1] when several chunks answer the same gold id. The cost:
  one chunk that covers two gold ids at once earns a single gain, so nDCG can
  understate that ranking.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping, Sequence


def _require_gold(gold: frozenset[str]) -> None:
    if not gold:
        raise ValueError("metric is undefined for a query with no gold items")


def _require_k(k: int) -> None:
    if k < 1:
        raise ValueError("k must be >= 1")


def _unique_matches(
    ranking: Sequence[Hashable], matches: Mapping[Hashable, frozenset[str]]
) -> list[frozenset[str]]:
    """Gold-match set per rank, after dropping repeated result ids."""
    seen: set[Hashable] = set()
    out: list[frozenset[str]] = []
    for result_id in ranking:
        if result_id in seen:
            continue
        seen.add(result_id)
        out.append(matches.get(result_id, frozenset()))
    return out


def hit_at_k(
    ranking: Sequence[Hashable],
    matches: Mapping[Hashable, frozenset[str]],
    gold: frozenset[str],
    k: int,
) -> float:
    """1.0 if any of the top k results is relevant, else 0.0."""
    _require_gold(gold)
    _require_k(k)
    top = _unique_matches(ranking, matches)[:k]
    return 1.0 if any(top) else 0.0


def recall_at_k(
    ranking: Sequence[Hashable],
    matches: Mapping[Hashable, frozenset[str]],
    gold: frozenset[str],
    k: int,
) -> float:
    """Share of gold ids covered by the top k results."""
    _require_gold(gold)
    _require_k(k)
    covered: set[str] = set()
    for match in _unique_matches(ranking, matches)[:k]:
        covered |= match & gold
    return len(covered) / len(gold)


def mrr(
    ranking: Sequence[Hashable],
    matches: Mapping[Hashable, frozenset[str]],
    gold: frozenset[str],
) -> float:
    """Reciprocal rank of the first relevant result, 0.0 if there is none."""
    _require_gold(gold)
    for position, match in enumerate(_unique_matches(ranking, matches), start=1):
        if match & gold:
            return 1.0 / position
    return 0.0


def ndcg_at_k(
    ranking: Sequence[Hashable],
    matches: Mapping[Hashable, frozenset[str]],
    gold: frozenset[str],
    k: int,
) -> float:
    """Binary-gain nDCG over the top k results, with the gain rule in the module doc."""
    _require_gold(gold)
    _require_k(k)
    covered: set[str] = set()
    dcg = 0.0
    for position, match in enumerate(_unique_matches(ranking, matches)[:k], start=1):
        new = (match & gold) - covered
        if new:
            dcg += 1.0 / math.log2(position + 1)
            covered |= new
    ideal = sum(1.0 / math.log2(p + 1) for p in range(1, min(len(gold), k) + 1))
    return dcg / ideal
