"""Minimal TMDB client.

Uses httpx + tenacity. Respects TMDB's 40 req / 10s budget via a simple
semaphore. Only the endpoints we actually need.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings


class TMDBClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._api_key = api_key
        self._sem = asyncio.Semaphore(10)   # ≤10 concurrent → well under budget

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        retrying = AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(
                (httpx.HTTPStatusError, httpx.TransportError)
            ),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                async with self._sem:
                    resp = await self._http.get(
                        f"{settings.tmdb_base_url}{path}",
                        params={"api_key": self._api_key, **params},
                    )
                    if resp.status_code == 429:
                        resp.raise_for_status()  # retried
                    resp.raise_for_status()
                    return resp.json()
        # unreachable
        raise RuntimeError("tenacity exited without yielding")

    async def get_genres(self) -> dict[str, Any]:
        return await self._get("/genre/movie/list", language="en-US")

    async def popular_movies(self, page: int = 1) -> dict[str, Any]:
        return await self._get("/movie/popular", language="en-US", page=page)

    async def movie_keywords(self, movie_id: int) -> dict[str, Any]:
        return await self._get(f"/movie/{movie_id}/keywords")
