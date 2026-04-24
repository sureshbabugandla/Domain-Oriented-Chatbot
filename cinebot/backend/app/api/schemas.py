"""Wire-format schemas.

All route inputs and outputs go through these — no leaking of ORM
objects to clients. Versioning is done by path (``/api/v1/``); when a
breaking change is required, branch the schema file and route prefix.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ── Auth ─────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserPublic(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Chat ─────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = Field(
        default=None,
        description="Resume an existing conversation. Omit to start a new one.",
    )
    message: str = Field(min_length=1, max_length=2000)


class RecommendationCard(BaseModel):
    movie_id: int
    title: str
    year: int | None
    poster_url: str | None
    score: float
    reasons: list[str]
    rendered: str


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    turn: int
    intent: str
    intent_confidence: float
    text: str
    recommendations: list[RecommendationCard]


# ── Feedback ─────────────────────────────────────────────
class FeedbackRequest(BaseModel):
    session_id: uuid.UUID
    movie_id: int
    signal: str = Field(
        description="one of: like | dislike | click | dismiss",
    )
    source_message_id: uuid.UUID | None = None


class FeedbackResponse(BaseModel):
    ok: bool = True
