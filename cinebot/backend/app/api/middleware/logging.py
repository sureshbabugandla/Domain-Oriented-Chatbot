"""Request logging + metrics middleware.

Attaches a request_id to structlog's contextvars so every log line emitted
during the request carries it. Records Prometheus histogram/counter entries
on the way out.
"""

from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.metrics import http_request_duration_seconds, http_requests_total


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
        )
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            elapsed = time.perf_counter() - start
            # Use the route template (not the realized path with IDs) as the
            # metric label so we don't blow up cardinality.
            route = request.scope.get("route")
            path_label = getattr(route, "path", request.url.path)
            http_requests_total.labels(
                method=request.method, path=path_label, status=str(status_code)
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method, path=path_label
            ).observe(elapsed)
            structlog.get_logger().info(
                "request_complete",
                status=status_code,
                latency_ms=round(elapsed * 1000, 1),
            )
