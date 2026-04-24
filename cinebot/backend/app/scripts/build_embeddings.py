"""Batch-embed every movie that lacks a vector.

Builds a representation string combining title + tagline + overview + genres
so the embedding captures both thematic content and categorical signal.

Run inside the container:
    python -m app.scripts.build_embeddings
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.core.logging import configure_logging, get_logger
from app.db.models import Movie
from app.db.session import SessionFactory, dispose_engine
from app.nlp.embedder import get_embedder

log = get_logger("embed")

BATCH = 64


def _representation(m: Movie) -> str:
    parts: list[str] = [m.title]
    if m.tagline:
        parts.append(m.tagline)
    if m.overview:
        parts.append(m.overview)
    if m.genres:
        parts.append("Genres: " + ", ".join(g.name for g in m.genres))
    return ". ".join(parts)


async def main() -> None:
    configure_logging()
    embedder = get_embedder()
    _ = embedder.model   # force load once

    processed = 0
    while True:
        async with SessionFactory() as db:
            stmt = (
                select(Movie)
                .where(Movie.embedding.is_(None))
                .order_by(Movie.id)
                .limit(BATCH)
            )
            batch = list((await db.execute(stmt)).scalars().all())
            if not batch:
                break

            texts = [_representation(m) for m in batch]
            vectors = await embedder.embed_many(texts)

            for movie, vec in zip(batch, vectors, strict=True):
                await db.execute(
                    update(Movie)
                    .where(Movie.id == movie.id)
                    .values(
                        embedding=vec,
                        embedding_updated_at=datetime.now(UTC),
                    )
                )
            await db.commit()
            processed += len(batch)
            log.info("batch_embedded", count=len(batch), total=processed)

    log.info("embed_complete", total=processed)
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
