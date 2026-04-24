"""Dialogue policy and turn orchestration.

The policy is rule-based: given the understood intent + current state,
decide the next action (answer, recommend, refine, ask for more, ack
feedback, end). Keeping policy rule-based here — rather than LLM-driven
— makes the flow auditable and predictable. LLM assistance is used only
for *response polishing*, not for choosing what to do.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import (
    nlp_inference_seconds,
    recommendation_latency_seconds,
    recommendations_served,
)
from app.db.models import IntentLabel
from app.db.repositories.movie_repo import MovieRepository
from app.db.repositories.user_repo import SessionRepository
from app.dialogue.response import compose_response
from app.dialogue.state import DialogueState, Slots
from app.nlp.pipeline import NLPPipeline, UnderstoodMessage, get_pipeline
from app.recommender.explainer import Explanation, build_explanations
from app.recommender.hybrid import Candidate, HybridRecommender
from app.recommender.ranker import apply_business_rules, rerank_mmr

if TYPE_CHECKING:
    from collections.abc import Sequence

log = get_logger("dialogue")

TOP_K = 5


@dataclass
class TurnResult:
    """Everything one chat turn produces."""

    text: str
    intent: str
    intent_confidence: float
    recommendations: list[Explanation]
    state: DialogueState

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "intent": self.intent,
            "intent_confidence": self.intent_confidence,
            "recommendations": [e.to_dict() for e in self.recommendations],
            "session_id": str(self.state.session_id),
            "turn": self.state.turn,
        }


class DialogueManager:
    """One instance per request. Holds the session + owns the turn flow."""

    def __init__(
        self,
        db: AsyncSession,
        state: DialogueState,
        nlp: NLPPipeline | None = None,
    ) -> None:
        self._db = db
        self._state = state
        self._nlp = nlp or get_pipeline()
        self._session_repo = SessionRepository(db)
        self._movie_repo = MovieRepository(db)

    async def handle(self, user_text: str) -> TurnResult:
        start = time.perf_counter()
        self._state.turn += 1

        # Persist user turn first — even if downstream crashes, we have the
        # raw text for debugging.
        await self._session_repo.append_message(
            session_id=self._state.session_id,
            role="user",
            content=user_text,
        )

        # NLP
        nlp_start = time.perf_counter()
        understood = await self._nlp.understand(user_text)
        nlp_inference_seconds.labels(stage="full").observe(time.perf_counter() - nlp_start)

        # Merge slots from this turn into session state.
        new_slots = _slots_from_entities(understood)
        self._state.slots = self._state.slots.merge(new_slots)

        # Dispatch on intent.
        recs: list[Explanation] = []
        if understood.intent == IntentLabel.RECOMMEND.value:
            recs = await self._do_recommend(understood, exclude=[])
        elif understood.intent == IntentLabel.REFINE.value:
            recs = await self._do_refine(understood)
        elif understood.intent == IntentLabel.MORE_INFO.value:
            # More-info is answered from state: pick the item mentioned
            # or the first one if unambiguous. The client usually has the
            # details already; we just confirm.
            recs = []
        # FEEDBACK handling lives in the feedback route — policy just acks.

        text = compose_response(
            intent=understood.intent,
            slots=self._state.slots,
            explanations=recs,
        )

        # Persist assistant turn + update session slots.
        await self._session_repo.append_message(
            session_id=self._state.session_id,
            role="assistant",
            content=text,
            intent=understood.intent,
            intent_confidence=understood.intent_confidence,
            entities=understood.entities.to_dict(),
        )
        await self._session_repo.update_slots(
            self._state.session_id, self._state.slots.model_dump()
        )
        if recs:
            rec_ids = [e.movie_id for e in recs]
            self._state.last_recommendation_ids = rec_ids
            await self._session_repo.set_last_recommendations(
                self._state.session_id, rec_ids
            )

        recommendation_latency_seconds.observe(time.perf_counter() - start)
        if recs:
            recommendations_served.labels(intent=understood.intent).inc()
        log.info(
            "turn_handled",
            intent=understood.intent,
            n_recs=len(recs),
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return TurnResult(
            text=text,
            intent=understood.intent,
            intent_confidence=understood.intent_confidence,
            recommendations=recs,
            state=self._state,
        )

    # ── Recommend path ───────────────────────────────────
    async def _do_recommend(
        self,
        understood: UnderstoodMessage,
        exclude: Sequence[int],
    ) -> list[Explanation]:
        if not understood.embedding:
            return []

        recommender = HybridRecommender(self._db)
        candidates = await recommender.recommend(
            understood=understood,
            user_id=self._state.user_id,
            exclude_ids=list(exclude) + self._state.last_recommendation_ids,
            limit=50,
        )
        if not candidates:
            return []

        apply_business_rules(candidates)
        top = rerank_mmr(candidates, k=TOP_K, lambda_relevance=0.7)
        return build_explanations(top, understood)

    async def _do_refine(self, understood: UnderstoodMessage) -> list[Explanation]:
        """Refine: use the last recommended items as the seed.

        If the user referenced a specific one ("more like the second"),
        we'd pick that single movie; otherwise we blend embeddings of the
        last slate. Keeping it simple here — seed from the whole slate.
        """
        if not self._state.last_recommendation_ids:
            return await self._do_recommend(understood, exclude=[])

        seeds = await self._movie_repo.get_by_ids(
            self._state.last_recommendation_ids[:3]
        )
        seeds_with_emb = [m for m in seeds if m.embedding is not None]
        if not seeds_with_emb:
            return await self._do_recommend(understood, exclude=[])

        # Average the seed embeddings to form a "theme" vector.
        import numpy as np
        theme = np.mean([np.asarray(m.embedding) for m in seeds_with_emb], axis=0)
        theme = theme / (np.linalg.norm(theme) or 1.0)

        # Replace the query embedding with the theme and re-run retrieve.
        synthetic = UnderstoodMessage(
            raw_text=understood.raw_text,
            normalized=understood.normalized,
            intent=IntentLabel.RECOMMEND.value,
            intent_confidence=understood.intent_confidence,
            entities=understood.entities,
            embedding=theme.tolist(),
        )
        return await self._do_recommend(
            synthetic, exclude=self._state.last_recommendation_ids
        )


def _slots_from_entities(u: UnderstoodMessage) -> Slots:
    return Slots(
        moods=u.entities.moods,
        descriptors=u.entities.descriptors,
        genre_ids=u.entities.genre_ids,
        genre_names=u.entities.genre_names,
        min_year=u.entities.min_year,
        max_year=u.entities.max_year,
        min_rating=u.entities.min_rating,
        max_runtime=u.entities.max_runtime,
        languages=u.entities.languages,
        age=u.entities.age,
    )


# ── Loader ───────────────────────────────────────────────
async def load_state(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> DialogueState:
    """Hydrate DialogueState from Postgres — called once per request."""
    repo = SessionRepository(db)
    session = await repo.get(session_id)
    if session is None:
        session = await repo.create(user_id)
    slots = Slots(**session.slots) if session.slots else Slots()
    return DialogueState(
        session_id=session.id,
        user_id=user_id,
        turn=len(session.messages),
        slots=slots,
        last_recommendation_ids=list(session.last_recommendation_ids or []),
    )
