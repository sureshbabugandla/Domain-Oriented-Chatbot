"""Feedback routes.

Explicit (like/dislike) writes to ``ratings``; implicit (click/dismiss)
writes to ``movie_impressions``. Both are handed off to Celery so the
request returns fast and persistence is retryable.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware.auth import get_current_active_user
from app.api.schemas import FeedbackRequest, FeedbackResponse
from app.core.metrics import feedback_total
from app.db.models import FeedbackSignal, User
from app.db.session import get_db
from app.workers.tasks import record_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_feedback(
    payload: FeedbackRequest,
    user: Annotated[User, Depends(get_current_active_user)],
    _: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackResponse:
    valid = {s.value for s in FeedbackSignal}
    if payload.signal not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"signal must be one of {sorted(valid)}",
        )

    feedback_total.labels(signal=payload.signal).inc()

    record_feedback.delay(
        user_id=str(user.id),
        session_id=str(payload.session_id),
        movie_id=payload.movie_id,
        signal=payload.signal,
        source_message_id=(
            str(payload.source_message_id)
            if payload.source_message_id is not None
            else None
        ),
    )
    return FeedbackResponse(ok=True)
