"""Hybrid recommender.

Content-based retrieval (vector kNN over movie embeddings) is the primary
signal — it works from day one and doesn't require user history. We blend
in a collaborative-filtering boost once the user has ≥5 ratings.

The CF component is intentionally simple: we aggregate what other users
with overlapping likes also liked (co-occurrence), then scale by the
liker count. A proper SVD/ALS model can drop in behind the same interface
when the dataset is large enough to warrant it — see `_cf_score`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Movie, Rating
from app.db.repositories.movie_repo import MovieRepository
from app.nlp.entity_extractor import Entities
from app.nlp.pipeline import UnderstoodMessage

if TYPE_CHECKING:
    from collections.abc import Sequence

log = get_logger("recommender.hybrid")


@dataclass
class Candidate:
    movie: Movie
    content_score: float         # cosine similarity, 0..1
    cf_score: float = 0.0        # normalized co-occurrence, 0..1
    final_score: float = 0.0
    reasons: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = []


class HybridRecommender:
    """Combines semantic vector search with collaborative filtering."""

    def __init__(
        self,
        session: AsyncSession,
        content_weight: float = 0.75,
        cf_weight: float = 0.25,
    ) -> None:
        self._db = session
        self._repo = MovieRepository(session)
        self._content_weight = content_weight
        self._cf_weight = cf_weight

    async def recommend(
        self,
        *,
        understood: UnderstoodMessage,
        user_id: uuid.UUID | None,
        exclude_ids: Sequence[int] = (),
        limit: int = 50,
    ) -> list[Candidate]:
        """Return candidates ranked by blended score, before MMR rerank."""
        if not understood.embedding:
            log.warning("recommend_no_embedding", intent=understood.intent)
            return []

        query_vector = await self._augment_query(understood)

        # ── Content-based retrieval ────────────────────
        content_hits = await self._repo.search_by_embedding(
            query_vector,
            limit=limit,
            genre_ids=understood.entities.genre_ids or None,
            min_year=understood.entities.min_year,
            max_year=understood.entities.max_year,
            min_rating=understood.entities.min_rating,
            exclude_ids=list(exclude_ids),
        )

        # Per-candidate object, preserving reasons for the explainer.
        candidates: dict[int, Candidate] = {}
        for movie, sim in content_hits:
            candidates[movie.id] = Candidate(
                movie=movie,
                content_score=sim,
                reasons=self._content_reasons(movie, understood.entities, sim),
            )

        # ── CF boost (if we have the user and enough signal) ─
        if user_id is not None:
            cf_scores = await self._cf_score(user_id, candidate_ids=list(candidates))
            for mid, score in cf_scores.items():
                if mid in candidates:
                    candidates[mid].cf_score = score
                    if score > 0.2:
                        candidates[mid].reasons.append(
                            "Popular with users who share your taste"
                        )

        # ── Blend ──────────────────────────────────────
        for c in candidates.values():
            c.final_score = (
                self._content_weight * c.content_score
                + self._cf_weight * c.cf_score
            )

        ranked = sorted(candidates.values(), key=lambda c: c.final_score, reverse=True)
        log.info(
            "candidates_scored",
            n=len(ranked),
            top=[(c.movie.id, round(c.final_score, 3)) for c in ranked[:5]],
        )
        return ranked

    # ── Helpers ──────────────────────────────────────────
    async def _augment_query(self, u: UnderstoodMessage) -> list[float]:
        """Mix the raw-query embedding with mood descriptors for richer recall.

        If moods are present, re-embed "{original}. {descriptors}" so the
        vector leans toward the semantic content the user actually wants.
        """
        if not u.entities.descriptors:
            return u.embedding
        from app.nlp.embedder import get_embedder
        augmented = u.normalized + ". " + ", ".join(u.entities.descriptors)
        return await get_embedder().embed(augmented)

    def _content_reasons(
        self, movie: Movie, ents: Entities, sim: float
    ) -> list[str]:
        reasons: list[str] = []
        if ents.genre_names:
            matched = [
                g.name.lower() for g in movie.genres
                if g.name.lower() in {n.lower() for n in ents.genre_names}
            ]
            if matched:
                reasons.append(f"Matches the {', '.join(matched)} you asked for")
        if ents.descriptors:
            reasons.append(
                "Captures a "
                + ", ".join(ents.descriptors[:2])
                + " mood"
            )
        if sim > 0.7:
            reasons.append("Very close thematic match")
        elif sim > 0.5:
            reasons.append("Thematically relevant")
        if movie.vote_average >= 8.0 and movie.vote_count > 500:
            reasons.append(
                f"Highly rated ({movie.vote_average:.1f}/10 from "
                f"{movie.vote_count:,} viewers)"
            )
        return reasons

    async def _cf_score(
        self, user_id: uuid.UUID, candidate_ids: Sequence[int]
    ) -> dict[int, float]:
        """Co-occurrence CF: for each candidate, count how many users who
        like the current user's favorites also liked the candidate.

        Normalized to [0, 1] by the max count in this batch. This avoids
        maintaining a separate ANN model while still giving a useful boost.
        """
        if not candidate_ids:
            return {}

        # Step 1: how many positive ratings does this user have?
        liked_stmt = select(Rating.movie_id).where(
            and_(Rating.user_id == user_id, Rating.value == 1)
        )
        liked = [r for (r,) in await self._db.execute(liked_stmt)]
        if len(liked) < 5:
            return {}

        # Step 2: find other users who liked ≥2 of those movies.
        peers_stmt = (
            select(Rating.user_id)
            .where(and_(Rating.movie_id.in_(liked), Rating.value == 1))
            .group_by(Rating.user_id)
            .having(func.count() >= 2)
        )
        peer_ids = [p for (p,) in await self._db.execute(peers_stmt)]
        if not peer_ids:
            return {}

        # Step 3: count co-occurrences against our candidates.
        co_stmt = (
            select(Rating.movie_id, func.count())
            .where(
                and_(
                    Rating.user_id.in_(peer_ids),
                    Rating.value == 1,
                    Rating.movie_id.in_(candidate_ids),
                )
            )
            .group_by(Rating.movie_id)
        )
        rows = list(await self._db.execute(co_stmt))
        if not rows:
            return {}

        counts = {int(mid): int(c) for mid, c in rows}
        mx = max(counts.values()) or 1
        return {mid: c / mx for mid, c in counts.items()}
