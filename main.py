"""FastAPI application entry point.

Wired here (and nowhere else):
  * Structured logging setup
  * Sentry (if DSN is set)
  * OpenTelemetry FastAPI instrumentation (if endpoint is set)
  * CORS, rate limit, request logging middleware (order matters)
  * All routers under /api/v1
  * /health, /ready, /metrics at the root
  * Global exception handler — never leak tracebacks to clients
  * Clean shutdown of DB pool + Redis client
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.middleware.logging import LoggingMiddleware
from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.routes import auth as auth_routes
from app.api.routes import chat as chat_routes
from app.api.routes import feedback as feedback_routes
from app.api.routes import health as health_routes
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis, get_redis
from app.db.session import dispose_engine

configure_logging()
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    log.info("app_starting", env=settings.app_env, version=__version__)

    # Warm the connection pools so the first request isn't slow.
    await get_redis().ping()

    # Sentry — opt-in via SENTRY_DSN.
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            release=f"cinebot@{__version__}",
            traces_sample_rate=0.1 if settings.is_production else 0,
            profiles_sample_rate=0.1 if settings.is_production else 0,
        )
        log.info("sentry_enabled")

    # OpenTelemetry — opt-in via OTEL_EXPORTER_OTLP_ENDPOINT.
    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": settings.app_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
            )
        )
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        log.info("otel_enabled")

    log.info("app_ready")
    yield
    log.info("app_stopping")
    await dispose_engine()
    await close_redis()
    log.info("app_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="CineBot API",
        description=(
            "Conversational movie recommender. "
            "Natural-language chat → intent + entities → hybrid retrieval → "
            "ranked, explained top-5."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ── Middleware — order matters: outer → inner  ──────
    # 1. CORS  (runs first on request, last on response)
    # 2. LoggingMiddleware (binds request_id for everything inside)
    # 3. RateLimitMiddleware (checks budget before hitting business logic)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["x-request-id", "x-ratelimit-remaining"],
    )
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # ── Routers ─────────────────────────────────────────
    app.include_router(health_routes.router)
    app.include_router(auth_routes.router, prefix="/api/v1")
    app.include_router(chat_routes.router, prefix="/api/v1")
    app.include_router(feedback_routes.router, prefix="/api/v1")

    # ── Global exception handler ────────────────────────
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", path=request.url.path)
        if settings.is_production:
            return JSONResponse(
                status_code=500, content={"detail": "internal server error"}
            )
        # Dev: include exception text to speed debugging.
        return JSONResponse(
            status_code=500, content={"detail": type(exc).__name__ + ": " + str(exc)}
        )

    @app.get("/", include_in_schema=False)
    async def _root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": __version__,
            "docs": "/docs",
        }

    return app


app = create_app()
