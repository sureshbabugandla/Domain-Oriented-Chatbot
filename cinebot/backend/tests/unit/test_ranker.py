"""Unit tests for the MMR reranker.

We construct synthetic Candidate objects with known embeddings so the
trade-off behavior is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from app.recommender.hybrid import Candidate
from app.recommender.ranker import apply_business_rules, rerank_mmr


@dataclass
class _FakeMovie:
    id: int
    title: str
    embedding: list[float]
    release_date: datetime | None = None
    vote_average: float = 7.0
    vote_count: int = 500


def _cand(
    id: int, title: str, embed: list[float], score: float, **kw: float
) -> Candidate:
    m = _FakeMovie(id=id, title=title, embedding=embed, **kw)     # type: ignore[arg-type]
    return Candidate(movie=m, content_score=score, final_score=score)  # type: ignore[arg-type]


@pytest.mark.unit
class TestMMR:
    def test_picks_first_by_relevance(self) -> None:
        cands = [
            _cand(1, "A", [1.0, 0.0, 0.0], 0.9),
            _cand(2, "B", [1.0, 0.0, 0.0], 0.8),   # same direction as A
            _cand(3, "C", [0.0, 1.0, 0.0], 0.7),   # orthogonal
        ]
        picked = rerank_mmr(cands, k=2, lambda_relevance=0.7)
        assert picked[0].movie.id == 1              # highest relevance first

    def test_diversifies_near_duplicates(self) -> None:
        """Given two similar top-score items + one dissimilar lower-score,
        MMR should pick the dissimilar one second."""
        cands = [
            _cand(1, "A", [1.0, 0.0, 0.0], 0.90),
            _cand(2, "A-clone", [0.99, 0.01, 0.0], 0.89),
            _cand(3, "Different", [0.0, 1.0, 0.0], 0.70),
        ]
        picked = rerank_mmr(cands, k=2, lambda_relevance=0.5)
        assert picked[0].movie.id == 1
        assert picked[1].movie.id == 3

    def test_short_lists_pass_through(self) -> None:
        cands = [_cand(1, "A", [1.0], 0.5), _cand(2, "B", [0.5], 0.4)]
        assert rerank_mmr(cands, k=5) == cands


@pytest.mark.unit
class TestBusinessRules:
    def test_fresh_movie_boosted(self) -> None:
        this_year = datetime.utcnow().year
        fresh = _cand(
            1, "Fresh", [1.0],
            score=0.5,
            release_date=datetime(this_year, 1, 1),
        )
        old = _cand(
            2, "Old", [1.0],
            score=0.5,
            release_date=datetime(this_year - 20, 1, 1),
        )
        apply_business_rules([fresh, old])
        assert fresh.final_score > old.final_score

    def test_low_vote_count_penalized(self) -> None:
        noisy = _cand(1, "Noisy", [1.0], score=1.0, vote_count=10)
        apply_business_rules([noisy])
        assert noisy.final_score < 1.0
