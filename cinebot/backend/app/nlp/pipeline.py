"""NLP pipeline — the single entry point used by the dialogue manager.

Given a raw user utterance, returns a structured ``UnderstoodMessage`` with
intent, confidence, entities, and a query embedding. Everything downstream
(dialogue policy, recommender) reads from this one object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.nlp.embedder import Embedder, get_embedder
from app.nlp.entity_extractor import Entities, extract
from app.nlp.intent_classifier import IntentClassifier, get_classifier
from app.nlp.preprocessor import normalize

log = get_logger("nlp.pipeline")


@dataclass
class UnderstoodMessage:
    raw_text: str
    normalized: str
    intent: str
    intent_confidence: float
    entities: Entities
    embedding: list[float] = field(default_factory=list)

    def to_log(self) -> dict[str, Any]:
        """Compact representation suitable for structured logs."""
        return {
            "intent": self.intent,
            "confidence": round(self.intent_confidence, 3),
            "entities": self.entities.to_dict(),
            "n_embedding": len(self.embedding),
        }


class NLPPipeline:
    """Stateless — safe to share across requests and async tasks."""

    def __init__(
        self,
        classifier: IntentClassifier | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._classifier = classifier or get_classifier()
        self._embedder = embedder or get_embedder()

    async def understand(
        self, text: str, *, with_embedding: bool = True
    ) -> UnderstoodMessage:
        """Run the full pipeline on one utterance."""
        normalized = normalize(text)
        intent, conf = self._classifier.classify(normalized)
        ents = extract(normalized)

        # Only embed for intents that will actually use the vector.
        need_embedding = with_embedding and intent in {"recommend", "refine"}
        embedding = await self._embedder.embed(normalized) if need_embedding else []

        msg = UnderstoodMessage(
            raw_text=text,
            normalized=normalized,
            intent=intent,
            intent_confidence=conf,
            entities=ents,
            embedding=embedding,
        )
        log.info("understood", **msg.to_log())
        return msg


_pipeline: NLPPipeline | None = None


def get_pipeline() -> NLPPipeline:
    """FastAPI-dependency-friendly singleton."""
    global _pipeline
    if _pipeline is None:
        _pipeline = NLPPipeline()
    return _pipeline
