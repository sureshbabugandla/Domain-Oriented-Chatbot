"""TMDB ingestion.

Pulls popular movies page-by-page, upserts into Postgres, and links genres.
Idempotent — safe to re-run. Rate-limited to respect TMDB's 40 req/10s budget.

Run inside the container:
    python -m app.scripts.ingest_tmdb
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.models import Genre, Movie
from app.db.session import SessionFactory, dispose_engine
from app.scripts._tmdb_client import TMDBClient

log = get_logger("ingest")


async def _ensure_genres(client: TMDBClient, db: AsyncSession) -> dict[int, Genre]:
    """Fetch TMDB genre list and upsert. Returns id → Genre map."""
    payload = await client.get_genres()
    by_id: dict[int, Genre] = {}
    for g in payload["genres"]:
        genre = Genre(id=g["id"], name=g["name"])
        merged = await db.merge(genre)
        by_id[int(g["id"])] = merged
    await db.flush()
    log.info("genres_ingested", count=len(by_id))
    return by_id


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


async def _ingest_page(
    client: TMDBClient,
    db: AsyncSession,
    page: int,
    genre_ids_known: set[int],
) -> int:
    """Ingest one page of popular movies into the *current* session.

    NOTE — we accept a set of known genre IDs (plain ints) rather than
    pre-loaded Genre ORM objects. ORM objects belong to a single session;
    re-using objects from a closed session into a fresh session raises
    InvalidRequestError. So we re-fetch the Genre rows by id in this
    session before linking them to the movie.
    """
    data = await client.popular_movies(page=page)
    count = 0
    for item in data["results"]:
        if item.get("adult"):
            continue
        movie = Movie(
            id=int(item["id"]),
            title=item["title"],
            original_title=item.get("original_title"),
            overview=item.get("overview"),
            release_date=_parse_date(item.get("release_date")),
            original_language=item.get("original_language"),
            popularity=float(item.get("popularity", 0.0)),
            vote_average=float(item.get("vote_average", 0.0)),
            vote_count=int(item.get("vote_count", 0)),
            poster_path=item.get("poster_path"),
            backdrop_path=item.get("backdrop_path"),
            adult=bool(item.get("adult", False)),
        )
        merged = await db.merge(movie)

        # Look up genres in THIS session — never reuse ORM objects from
        # a different (or closed) session.
        wanted_ids = [
            gid for gid in item.get("genre_ids", []) if gid in genre_ids_known
        ]
        if wanted_ids:
            stmt = select(Genre).where(Genre.id.in_(wanted_ids))
            merged.genres = list((await db.execute(stmt)).scalars().all())
        else:
            merged.genres = []
        count += 1
    await db.flush()
    return count


async def main() -> None:
    configure_logging()
    if not settings.tmdb_api_key:
        log.warning("tmdb_api_key_missing", msg="Skipping ingest; seed file only.")
        return

    async with httpx.AsyncClient(timeout=20.0) as http:
        client = TMDBClient(http=http, api_key=settings.tmdb_api_key)

        # First session: ensure genres exist. We capture only the IDs
        # (primitive ints) to pass into per-page sessions later.
        async with SessionFactory() as db:
            genres_by_id = await _ensure_genres(client, db)
            await db.commit()
        known_genre_ids: set[int] = set(genres_by_id.keys())

        total = 0
        for page in range(1, settings.tmdb_ingest_pages + 1):
            try:
                async with SessionFactory() as page_db:
                    n = await _ingest_page(client, page_db, page, known_genre_ids)
                    await page_db.commit()
                    total += n
                    log.info("page_ingested", page=page, count=n, total=total)
            except httpx.HTTPStatusError as e:
                log.error("page_failed", page=page, status=e.response.status_code)
                if e.response.status_code == 429:  # rate limited
                    await asyncio.sleep(5)

        # Final report — how many still need embeddings next.
        async with SessionFactory() as post_db:
            missing = await post_db.execute(
                select(Movie.id).where(Movie.embedding.is_(None))
            )
            missing_count = len(list(missing))
            log.info(
                "ingest_complete",
                total=total,
                pending_embeddings=missing_count,
            )

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())