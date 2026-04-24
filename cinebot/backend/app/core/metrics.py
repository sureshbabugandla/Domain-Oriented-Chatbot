"""Prometheus metrics.

Register once at module import. Middleware records request-level metrics;
the dialogue manager and recommender record their own timers.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)

# ── HTTP ─────────────────────────────────────────────────
http_requests_total = Counter(
    "cinebot_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "cinebot_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=REGISTRY,
)

# ── NLP / recommender ────────────────────────────────────
nlp_inference_seconds = Histogram(
    "cinebot_nlp_inference_seconds",
    "Time spent in NLP pipeline",
    ["stage"],  # intent | ner | embed | full
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=REGISTRY,
)

recommendations_served = Counter(
    "cinebot_recommendations_served_total",
    "Count of recommendation slates returned",
    ["intent"],
    registry=REGISTRY,
)

recommendation_latency_seconds = Histogram(
    "cinebot_recommendation_latency_seconds",
    "Full chat-turn latency (NLP + retrieval + rerank + explain)",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
    registry=REGISTRY,
)

# ── LLM ──────────────────────────────────────────────────
llm_requests_total = Counter(
    "cinebot_llm_requests_total",
    "LLM calls by provider and outcome",
    ["provider", "outcome"],  # ok | retry | failure
    registry=REGISTRY,
)

llm_latency_seconds = Histogram(
    "cinebot_llm_latency_seconds",
    "Latency of LLM complete/stream calls",
    ["provider"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)

# ── Feedback ─────────────────────────────────────────────
feedback_total = Counter(
    "cinebot_feedback_total",
    "Feedback signals received",
    ["signal"],  # like | dislike | click | dismiss
    registry=REGISTRY,
)
