"""Ranking and diversity.

Maximal Marginal Relevance (MMR) trades off relevance (blended score) vs
novelty (distance from already-picked items). Pure relevance ranking
often returns 5 slight variants of the same film; MMR surfaces a more
interesting slate.

We also apply a freshness nudge so recent films get a small boost, and a
popularity floor so we don't surface obscure weirdness the user can't
find anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import numpy as np

from app.core.logging import get_logger
from app.recommender.hybrid import Candidate

log = get_logger("recommender.ranker")


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    va, vb = np.asarray(a), np.asarray(b)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def apply_business_rules(
    candidates: list[Candidate],
    *,
    freshness_boost: float = 0.05,
) -> list[Candidate]:
    """Small relevance tweaks that aren't learned."""
    current_year = datetime.utcnow().year
    for c in candidates:
        if c.movie.release_date:
            age = current_year - c.movie.release_date.year
            # Movies from the last 5 years get up to +0.05; older get 0.
            if age <= 5:
                c.final_score += freshness_boost * (1 - age / 5)
        # Small penalty for low-vote films — protects against noise.
        if c.movie.vote_count < 50:
            c.final_score *= 0.85
    return candidates


def rerank_mmr(
    candidates: list[Candidate],
    *,
    k: int = 5,
    lambda_relevance: float = 0.7,
) -> list[Candidate]:
    """Greedy MMR: at each step, pick the item maximizing
    ``λ · score − (1−λ) · max_sim_to_selected``.

    ``lambda_relevance`` close to 1 ⇒ pure relevance; close to 0 ⇒
    pure diversity. 0.7 works well empirically for recommender slates.
    """
    if len(candidates) <= k:
        return candidates

    with_embed = [c for c in candidates if c.movie.embedding is not None]
    if not with_embed:
        return candidates[:k]

    selected: list[Candidate] = []
    pool = with_embed[:]

    # Seed with the top-scoring item.
    first = max(pool, key=lambda c: c.final_score)
    selected.append(first)
    pool.remove(first)

    while pool and len(selected) < k:

        def mmr(c: Candidate) -> float:
            # c.movie.embedding is non-None by filter above — narrow for mypy.
            assert c.movie.embedding is not None
            diversity = max(
                _cosine(c.movie.embedding, s.movie.embedding)  # type: ignore[arg-type]
                for s in selected
            )
            return lambda_relevance * c.final_score - (1 - lambda_relevance) * diversity

        best = max(pool, key=mmr)
        selected.append(best)
        pool.remove(best)

    log.info(
        "mmr_selected",
        n=len(selected),
        ids=[c.movie.id for c in selected],
        λ=lambda_relevance,
    )
    return selected
