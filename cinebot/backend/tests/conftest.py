"""Shared pytest fixtures.

Integration tests that need Postgres/Redis live under tests/integration and
spin up containers via testcontainers — fixtures for those live in that
directory's conftest so unit runs stay fast.
"""

from __future__ import annotations

import os

# Set required settings *before* app.core.config is imported anywhere.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-at-least-16-chars-long")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://cinebot:cinebot@localhost:5432/cinebot_test",
)
os.environ.setdefault(
    "SYNC_DATABASE_URL",
    "postgresql://cinebot:cinebot@localhost:5432/cinebot_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_CELERY_BROKER", "redis://localhost:6379/2")
os.environ.setdefault("REDIS_CELERY_BACKEND", "redis://localhost:6379/3")
os.environ.setdefault("TMDB_API_KEY", "test-fake-key")
