"""Sentence embedding service.

One model loaded per process, lazily. The API is async-friendly (uses
`asyncio.to_thread` to avoid blocking the event loop) and batches
internally for throughput.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Sequence
from functools import cached_property

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.logging import get_logger
from app.nlp.preprocessor import normalize

log = get_logger("embedder")


class Embedder:
    """Thread-safe singleton wrapper around a SentenceTransformer model."""

    _instance: "Embedder | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "Embedder":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    @cached_property
    def model(self) -> SentenceTransformer:
        log.info("embedder_loading", model=settings.embedding_model)
        m = SentenceTransformer(settings.embedding_model)
        # Warm up — first forward pass is slow.
        m.encode(["warmup"], show_progress_bar=False)
        log.info("embedder_ready", dim=m.get_sentence_embedding_dimension())
        return m

    @property
    def dimension(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    # ── Sync core — run in executor from async callers ──────
    def _encode_batch(self, texts: Sequence[str]) -> np.ndarray:
        cleaned = [normalize(t) for t in texts]
        return self.model.encode(
            cleaned,
            batch_size=settings.embedding_batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,    # unit-length → cosine == dot
            show_progress_bar=False,
        )

    async def embed(self, text: str) -> list[float]:
        vec = await asyncio.to_thread(self._encode_batch, [text])
        return vec[0].tolist()

    async def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        mat = await asyncio.to_thread(self._encode_batch, list(texts))
        return [row.tolist() for row in mat]


def get_embedder() -> Embedder:
    """Importable factory — swap in tests with dependency_overrides."""
    return Embedder()
