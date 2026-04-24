"""Rate-limit middleware.

Keys on the authenticated user when present, falling back to the client
IP. Skips /health, /ready, /metrics, and docs — those must be reachable
for liveness checks and operator tooling.
"""

from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.redis import RateLimiter, get_redis
from app.core.security import decode_token

SKIP_PREFIXES = ("/health", "/ready", "/metrics", "/docs", "/openapi.json", "/redoc")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if any(request.url.path.startswith(p) for p in SKIP_PREFIXES):
            return await call_next(request)

        identity = self._identity(request)
        limiter = RateLimiter(get_redis())
        allowed, remaining = await limiter.check(identity)

        if not allowed:
            return Response(
                content='{"detail":"rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "1"},
            )
        response = await call_next(request)
        response.headers["x-ratelimit-remaining"] = str(remaining)
        return response

    def _identity(self, request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            try:
                payload = decode_token(auth[7:])
                return f"u:{payload.sub}"
            except ValueError:
                pass
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"
