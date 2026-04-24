"""Health, readiness, and metrics endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.metrics import REGISTRY
from app.core.redis import get_redis
from app.db.session import get_db

router = APIRouter(tags=["ops"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Cheap — returns immediately. Used by the k8s livenessProbe."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe — checks dependencies")
async def ready(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Used by k8s readinessProbe. Fails (503) until Postgres + Redis answer."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return Response(                             # type: ignore[return-value]
            content='{"postgres":"down"}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        )
    try:
        pong = await get_redis().ping()
        if not pong:
            raise RuntimeError("redis ping failed")
    except Exception:
        return Response(                             # type: ignore[return-value]
            content='{"redis":"down"}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        )
    return {"status": "ready"}


@router.get("/metrics", summary="Prometheus scrape endpoint")
async def metrics() -> Response:
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
