"""User and session persistence — small and boring on purpose."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Message, Session, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def update_preferences(
        self, user_id: uuid.UUID, preferences: dict[str, Any]
    ) -> None:
        user = await self.get(user_id)
        if user is None:
            return
        merged = {**user.preferences, **preferences}
        user.preferences = merged


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, session_id: uuid.UUID) -> Session | None:
        stmt = (
            select(Session)
            .options(selectinload(Session.messages))
            .where(Session.id == session_id)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(self, user_id: uuid.UUID) -> Session:
        session = Session(user_id=user_id)
        self._session.add(session)
        await self._session.flush()
        return session

    async def update_slots(
        self, session_id: uuid.UUID, slots: dict[str, Any]
    ) -> None:
        s = await self.get(session_id)
        if s is None:
            return
        s.slots = {**s.slots, **slots}

    async def append_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        intent: str | None = None,
        intent_confidence: float | None = None,
        entities: dict[str, Any] | None = None,
    ) -> Message:
        msg = Message(
            session_id=session_id,
            role=role,
            content=content,
            intent=intent,
            intent_confidence=intent_confidence,
            entities=entities or {},
        )
        self._session.add(msg)
        await self._session.flush()
        return msg

    async def set_last_recommendations(
        self, session_id: uuid.UUID, movie_ids: list[int]
    ) -> None:
        s = await self.get(session_id)
        if s is None:
            return
        s.last_recommendation_ids = movie_ids
