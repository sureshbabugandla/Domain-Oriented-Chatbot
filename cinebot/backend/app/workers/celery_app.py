"""Celery application.

Two roles:
  * Ingest/ML backfill jobs (embedding generation, intent retraining).
  * Async write-path tasks (persisting feedback, aggregating ratings).

Everything is routed through Redis. ``task_always_eager`` flips tasks to
synchronous execution for unit tests.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "cinebot",
    broker=str(settings.redis_celery_broker),
    backend=str(settings.redis_celery_backend),
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,            # fair queueing for heavy tasks
    worker_max_tasks_per_child=500,          # recycle to bound mem growth
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    task_time_limit=300,
    task_soft_time_limit=240,
)

# Periodic jobs — nightly embedding refresh for any new movies.
celery_app.conf.beat_schedule = {
    "embed-new-movies": {
        "task": "app.workers.tasks.embed_missing_movies",
        "schedule": crontab(hour=3, minute=0),     # 03:00 UTC
        "options": {"queue": "default"},
    },
}
