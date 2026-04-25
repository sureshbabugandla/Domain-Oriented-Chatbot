"""Typed settings loaded from environment variables.

Import as:
    from app.core.config import settings

Every module pulls config from here — never reads os.environ directly.
Settings are frozen; tests override via pytest fixtures with a fresh instance.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "cinebot"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api_host: str = "0.0.0.0"  # noqa: S104  # bind all in container
    api_port: int = 8000
    cors_origins: str | list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # ── Auth ─────────────────────────────────────────────
    jwt_secret_key: str = Field(min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # ── Databases ────────────────────────────────────────
    database_url: PostgresDsn
    sync_database_url: PostgresDsn
    redis_url: RedisDsn
    redis_cache_db: int = 1
    redis_celery_broker: RedisDsn
    redis_celery_backend: RedisDsn

    # ── Rate limit ───────────────────────────────────────
    rate_limit_per_minute: int = 100
    rate_limit_burst: int = 20

    # ── LLM ──────────────────────────────────────────────
    llm_provider: Literal["openai", "ollama"] = "ollama"
    llm_timeout_seconds: int = 15
    llm_max_retries: int = 2
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.4
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_temperature: float = 0.4

    # ── Embeddings & NLP ─────────────────────────────────
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    embedding_batch_size: int = 64
    intent_model_path: str = "/app/ml/models/intent_classifier"
    spacy_model: str = "en_core_web_sm"
    intent_confidence_threshold: float = 0.60

    # ── TMDB ─────────────────────────────────────────────
    tmdb_api_key: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_image_base: str = "https://image.tmdb.org/t/p/w500"
    tmdb_ingest_pages: int = 50

    # ── Celery ───────────────────────────────────────────
    celery_task_always_eager: bool = False
    celery_worker_concurrency: int = 4

    # ── Observability ────────────────────────────────────
    mlflow_tracking_uri: str = "http://mlflow:5000"
    otel_exporter_otlp_endpoint: str = ""
    sentry_dsn: str = ""
    prometheus_metrics_path: str = "/metrics"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor — instantiated once per process."""
    return Settings()  # type: ignore[call-arg]


# Module-level convenience. Prefer dependency injection in routes.
settings = get_settings()
