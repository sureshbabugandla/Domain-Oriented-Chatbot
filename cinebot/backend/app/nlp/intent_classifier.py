"""Intent classification.

Primary: fine-tuned DistilBERT at ``settings.intent_model_path``.
Fallback: rule-based classifier so the app works on a cold clone without
first running training. Both satisfy the same interface.

The classifier returns (label, confidence). Confidences below
``settings.intent_confidence_threshold`` are downgraded to ``oos``.
"""

from __future__ import annotations

import re
import threading
from functools import cached_property
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import IntentLabel

log = get_logger("intent")


class IntentClassifier(Protocol):
    def classify(self, text: str) -> tuple[str, float]: ...


# ── Rule-based fallback ───────────────────────────────────
_RULES: list[tuple[re.Pattern[str], IntentLabel]] = [
    (re.compile(r"\b(hi|hello|hey|yo|hiya|good (?:morning|evening|afternoon))\b", re.I),
     IntentLabel.GREET),
    (re.compile(r"\b(bye|goodbye|see you|later|that'?s all|thanks?,? bye)\b", re.I),
     IntentLabel.GOODBYE),
    (re.compile(r"\b(more like|similar|another|show (?:me )?more|something like (?:the|that|it))\b", re.I),
     IntentLabel.REFINE),
    (re.compile(r"\b(tell me more|more info|what'?s it about|details?|plot)\b", re.I),
     IntentLabel.MORE_INFO),
    (re.compile(r"\b(i (?:liked|loved|enjoyed|hated|didn'?t like)|thumbs up|thumbs down|not my thing)\b", re.I),
     IntentLabel.FEEDBACK),
    (re.compile(
        r"\b(recommend|suggest|watch|movie|film|looking for|in the mood for|something (?:to watch|fun|scary))\b",
        re.I,
    ), IntentLabel.RECOMMEND),
]


class RuleBasedClassifier:
    """Zero-dependency fallback. Good enough to smoke-test the stack."""

    def classify(self, text: str) -> tuple[str, float]:
        t = text.strip()
        if not t:
            return IntentLabel.OOS.value, 1.0
        for pattern, label in _RULES:
            if pattern.search(t):
                # Confidence is heuristic — keep below the true-model
                # threshold so it's obvious when the fallback is in use.
                return label.value, 0.75
        return IntentLabel.OOS.value, 0.5


# ── Transformer-based classifier ──────────────────────────
class TransformerClassifier:
    """Loads a fine-tuned DistilBERT sequence classifier."""

    _instance: "TransformerClassifier | None" = None
    _lock = threading.Lock()

    def __new__(cls, model_path: str) -> "TransformerClassifier":
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._model_path = model_path  # type: ignore[attr-defined]
                cls._instance = inst
        return cls._instance  # type: ignore[return-value]

    @cached_property
    def _pipeline(self):  # type: ignore[no-untyped-def]
        from transformers import pipeline
        log.info("intent_model_loading", path=self._model_path)  # type: ignore[attr-defined]
        return pipeline(
            "text-classification",
            model=self._model_path,           # type: ignore[attr-defined]
            tokenizer=self._model_path,       # type: ignore[attr-defined]
            top_k=None,
            truncation=True,
            max_length=128,
        )

    def classify(self, text: str) -> tuple[str, float]:
        preds = self._pipeline(text.strip() or " ")[0]
        # preds is a list of {label, score} — pick argmax.
        best = max(preds, key=lambda p: p["score"])
        label = best["label"].lower()
        score = float(best["score"])
        if score < settings.intent_confidence_threshold:
            return IntentLabel.OOS.value, score
        return label, score


# ── Factory ───────────────────────────────────────────────
_classifier: IntentClassifier | None = None
_classifier_lock = threading.Lock()


def get_classifier() -> IntentClassifier:
    """Return the best classifier available, lazily."""
    global _classifier
    if _classifier is not None:
        return _classifier
    with _classifier_lock:
        if _classifier is not None:
            return _classifier
        path = Path(settings.intent_model_path)
        if path.exists() and (path / "config.json").exists():
            _classifier = TransformerClassifier(str(path))
            log.info("intent_using", kind="transformer")
        else:
            _classifier = RuleBasedClassifier()
            log.warning(
                "intent_using",
                kind="rule_based",
                reason="fine-tuned model not found — run `make train-intent` for production",
            )
    return _classifier
