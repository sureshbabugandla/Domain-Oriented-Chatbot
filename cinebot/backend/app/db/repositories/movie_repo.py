"""Movie repository — all movie queries go through here.

Keeping SQL in the repo layer means:
  * Services stay testable with an in-memory fake.
  * We can tune indexes / rewrite queries without touching business logic.
  * The vector-search incantation is documented once.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Genre, Movie


class MovieRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Reads ────────────────────────────────────────────
    async def get_by_id(self, movie_id: int) -> Movie | None:
        stmt = (
            select(Movie)
            .options(selectinload(Movie.genres))
            .where(Movie.id == movie_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_ids(self, ids: Sequence[int]) -> list[Movie]:
        if not ids:
            return []
        stmt = (
            select(Movie)
            .options(selectinload(Movie.genres))
            .where(Movie.id.in_(ids))
        )
        result = await self._session.execute(stmt)
        # Preserve requested order for ranking stability.
        by_id = {m.id: m for m in result.scalars().all()}
        return [by_id[i] for i in ids if i in by_id]

    async def search_by_title(self, query: str, limit: int = 10) -> list[Movie]:
        """Fuzzy title search using pg_trgm similarity."""
        similarity = func.similarity(Movie.title, query)
        stmt = (
            select(Movie)
            .options(selectinload(Movie.genres))
            .where(similarity > 0.2)
            .order_by(similarity.desc(), Movie.popularity.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def search_by_embedding(
        self,
        embedding: list[float],
        *,
        limit: int = 50,
        genre_ids: Sequence[int] | None = None,
        min_year: int | None = None,
        max_year: int | None = None,
        min_rating: float | None = None,
        exclude_ids: Sequence[int] | None = None,
    ) -> list[tuple[Movie, float]]:
        """kNN against the HNSW index. Returns (movie, similarity) desc.

        Uses the <=> cosine-distance operator, so we flip it to similarity
        (1 - distance) before returning. Filters are applied pre-kNN via
        the WHERE clause so HNSW pruning still works.
        """
        distance = Movie.embedding.cosine_distance(embedding)  # type: ignore[attr-defined]

        conditions = [Movie.embedding.isnot(None)]
        if min_rating is not None:
            conditions.append(Movie.vote_average >= min_rating)
        if min_year is not None:
            conditions.append(func.extract("year", Movie.release_date) >= min_year)
        if max_year is not None:
            conditions.append(func.extract("year", Movie.release_date) <= max_year)
        if exclude_ids:
            conditions.append(Movie.id.notin_(exclude_ids))

        stmt = (
            select(Movie, distance.label("distance"))
            .options(selectinload(Movie.genres))
            .where(and_(*conditions))
            .order_by(distance)
            .limit(limit)
        )

        # Genre filter requires a join; apply after base stmt for clarity.
        if genre_ids:
            stmt = stmt.join(Movie.genres).where(Genre.id.in_(genre_ids))

        result = await self._session.execute(stmt)
        return [(m, 1.0 - float(d)) for m, d in result.all()]

    async def popular(
        self, limit: int = 20, genre_ids: Sequence[int] | None = None
    ) -> list[Movie]:
        stmt = (
            select(Movie)
            .options(selectinload(Movie.genres))
            .where(Movie.vote_count > 100)
            .order_by(Movie.popularity.desc())
            .limit(limit)
        )
        if genre_ids:
            stmt = stmt.join(Movie.genres).where(Genre.id.in_(genre_ids))
        return list((await self._session.execute(stmt)).scalars().all())

    # ── Writes ───────────────────────────────────────────
    async def upsert(self, movie: Movie) -> None:
        """Insert or update by TMDB id. Called by ingest script."""
        merged = await self._session.merge(movie)
        self._session.add(merged)

    async def set_embedding(
        self, movie_id: int, embedding: list[float]
    ) -> None:
        await self._session.execute(
            Movie.__table__.update()
            .where(Movie.id == movie_id)
            .values(embedding=embedding, embedding_updated_at=func.now())
        )

    async def count_without_embedding(self) -> int:
        stmt = select(func.count(Movie.id)).where(
            or_(Movie.embedding.is_(None), Movie.embedding_updated_at.is_(None))
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def iter_without_embedding(
        self, batch_size: int = 100
    ) -> list[Movie]:
        stmt = (
            select(Movie)
            .options(selectinload(Movie.genres))
            .where(
                or_(
                    Movie.embedding.is_(None),
                    Movie.embedding_updated_at.is_(None),
                )
            )
            .order_by(Movie.id)
            .limit(batch_size)
        )
        return list((await self._session.execute(stmt)).scalars().all())
