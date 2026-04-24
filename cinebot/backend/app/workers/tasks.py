"""Celery task implementations.

These bridge async-DB code into Celery's sync worker model. We create a
short-lived asyncio event loop per task — simple, avoids polluting the
worker with a persistent loop, and lets each task run under the same
``SessionFactory`` everything else uses.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from app.core.logging import configure_logging, get_logger
from app.db.models import FeedbackSignal, Movie, MovieImpression, Rating
from app.db.session import SessionFactory, dispose_engine
from app.workers.celery_app import celery_app

log = get_logger("worker")

# ── Boot-time logging for the worker process ────────────
configure_logging()


def _run(coro: Any) -> Any:
    """Execute an async coroutine from sync Celery code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(dispose_engine())
        loop.close()


# ── Feedback persistence ─────────────────────────────────
@celery_app.task(
    name="app.workers.tasks.record_feedback",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def record_feedback(
    self: Any,                                                       # noqa: ARG001
    *,
    user_id: str,
    session_id: str,
    movie_id: int,
    signal: str,
    source_message_id: str | None = None,
) -> None:
    async def _go() -> None:
        async with SessionFactory() as db:
            if signal in {FeedbackSignal.LIKE.value, FeedbackSignal.DISLIKE.value}:
                value = 1 if signal == FeedbackSignal.LIKE.value else -1
                existing = await db.execute(
                    select(Rating).where(
                        Rating.user_id == uuid.UUID(user_id),
                        Rating.movie_id == movie_id,
                    )
                )
                row = existing.scalar_one_or_none()
                if row is None:
                    db.add(
                        Rating(
                            user_id=uuid.UUID(user_id),
                            movie_id=movie_id,
                            value=value,
                            source_message_id=(
                                uuid.UUID(source_message_id)
                                if source_message_id
                                else None
                            ),
                        )
                    )
                else:
                    row.value = value
            else:
                # Implicit signals (click / dismiss) go to impressions.
                db.add(
                    MovieImpression(
                        session_id=uuid.UUID(session_id),
                        movie_id=movie_id,
                        rank=0,
                        signal=signal,
                    )
                )
            await db.commit()
        log.info("feedback_persisted", signal=signal, movie_id=movie_id)

    _run(_go())


# ── Embedding backfill ───────────────────────────────────
@celery_app.task(name="app.workers.tasks.embed_missing_movies")
def embed_missing_movies(limit: int = 200) -> int:
    """Runs on cron — embeds movies added since last run."""
    from app.nlp.embedder import get_embedder

    async def _go() -> int:
        embedder = get_embedder()
        processed = 0
        async with SessionFactory() as db:
            stmt = (
                select(Movie)
                .where(Movie.embedding.is_(None))
                .order_by(Movie.id)
                .limit(limit)
            )
            batch = list((await db.execute(stmt)).scalars().all())
            if not batch:
                return 0

            texts = [
                ". ".join(filter(None, [m.title, m.tagline, m.overview or ""]))
                for m in batch
            ]
            vecs = await embedder.embed_many(texts)
            for movie, vec in zip(batch, vecs, strict=True):
                await db.execute(
                    update(Movie)
                    .where(Movie.id == movie.id)
                    .values(
                        embedding=vec,
                        embedding_updated_at=datetime.now(UTC),
                    )
                )
                processed += 1
            await db.commit()
        log.info("embed_backfill_complete", n=processed)
        return processed

    return _run(_go())
