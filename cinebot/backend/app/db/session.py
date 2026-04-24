"""Async SQLAlchemy engine and session factory.

The engine is created once at module import and reused by all requests.
Pool sizes are conservative defaults — tune via env in prod.

Usage in routes:

    from app.db.session import get_db

    @router.get("/movies/{id}")
    async def read_movie(id: int, db: AsyncSession = Depends(get_db)):
        ...
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _build_engine() -> AsyncEngine:
    """Create engine with production-safe pool settings."""
    return create_async_engine(
        str(settings.database_url),
        echo=False,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,       # drop stale conns after RDS failover
        pool_recycle=1800,        # 30min — under most LB idle timeouts
        future=True,
    )


engine: AsyncEngine = _build_engine()

# expire_on_commit=False so objects remain usable after commit — needed for
# streaming responses where we serialize ORM objects post-commit.
SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session with automatic close."""
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Call on app shutdown to close the pool cleanly."""
    await engine.dispose()


# Passed to Alembic to avoid it recreating the engine.
def get_engine_kwargs() -> dict[str, Any]:
    return {"url": str(settings.sync_database_url)}
