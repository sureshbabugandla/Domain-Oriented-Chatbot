"""Dialogue state model.

State lives in Postgres (authoritative) and is cached in Redis for fast
mid-conversation reads. Slots persist across turns so a refine intent
(``more like the second one``) has something to refine.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class Slots(BaseModel):
    """Cumulative user preferences across a session."""

    moods: list[str] = Field(default_factory=list)
    descriptors: list[str] = Field(default_factory=list)
    genre_ids: list[int] = Field(default_factory=list)
    genre_names: list[str] = Field(default_factory=list)
    min_year: int | None = None
    max_year: int | None = None
    min_rating: float | None = None
    max_runtime: int | None = None
    languages: list[str] = Field(default_factory=list)
    age: int | None = None

    def merge(self, other: "Slots") -> "Slots":
        """Later-message values override earlier ones for scalars; lists
        are union-ed. This lets 'actually, make it 90s' update era without
        clearing the mood slot."""
        return Slots(
            moods=list(dict.fromkeys([*self.moods, *other.moods])),
            descriptors=list(dict.fromkeys([*self.descriptors, *other.descriptors])),
            genre_ids=list(dict.fromkeys([*self.genre_ids, *other.genre_ids])),
            genre_names=list(dict.fromkeys([*self.genre_names, *other.genre_names])),
            min_year=other.min_year or self.min_year,
            max_year=other.max_year or self.max_year,
            min_rating=other.min_rating or self.min_rating,
            max_runtime=other.max_runtime or self.max_runtime,
            languages=list(dict.fromkeys([*self.languages, *other.languages])),
            age=other.age or self.age,
        )


class DialogueState(BaseModel):
    session_id: uuid.UUID
    user_id: uuid.UUID
    turn: int = 0
    slots: Slots = Field(default_factory=Slots)
    last_recommendation_ids: list[int] = Field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        """Dict representation for persistence."""
        return self.model_dump(mode="json")
