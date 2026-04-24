"""Chat routes.

``POST /chat`` is the simple request/response form.
``WS   /chat/stream`` is the streaming form — tokens are flushed as the
LLM generates them, with a final JSON ``done`` frame carrying the
recommendation cards.

Auth on the WebSocket uses a query-string bearer token since browsers
can't set custom WS headers.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware.auth import get_current_active_user
from app.api.schemas import ChatRequest, ChatResponse, RecommendationCard
from app.core.logging import get_logger
from app.core.security import decode_token
from app.db.models import User
from app.db.repositories.user_repo import SessionRepository, UserRepository
from app.db.session import SessionFactory, get_db
from app.dialogue.policy import DialogueManager, load_state

router = APIRouter(prefix="/chat", tags=["chat"])
log = get_logger("api.chat")


def _to_cards(recs: list) -> list[RecommendationCard]:
    return [
        RecommendationCard(
            movie_id=e.movie_id,
            title=e.title,
            year=e.year,
            poster_url=e.poster_url,
            score=e.score,
            reasons=e.reasons,
            rendered=e.rendered,
        )
        for e in recs
    ]


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChatResponse:
    """One full turn: accept a message, return text + recommendations."""
    session_id = payload.session_id
    if session_id is None:
        new_session = await SessionRepository(db).create(user.id)
        await db.commit()
        session_id = new_session.id

    state = await load_state(db, session_id=session_id, user_id=user.id)
    manager = DialogueManager(db, state)
    result = await manager.handle(payload.message)
    await db.commit()

    return ChatResponse(
        session_id=result.state.session_id,
        turn=result.state.turn,
        intent=result.intent,
        intent_confidence=result.intent_confidence,
        text=result.text,
        recommendations=_to_cards(result.recommendations),
    )


@router.websocket("/stream")
async def chat_stream(ws: WebSocket, token: str | None = None) -> None:
    """Streaming chat.

    Wire protocol:
      client → server:  {"session_id": <uuid|null>, "message": "..."}
      server → client:  {"type":"token","content":"Here"} (n of these)
                        {"type":"done","payload": <ChatResponse>}
                        {"type":"error","detail":"..."}
    """
    await ws.accept()

    # Authenticate. Wire protocol allows token either as ?token= or as
    # the first message's "auth" field to keep the URL clean.
    user_id = await _authenticate_ws(ws, token)
    if user_id is None:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        while True:
            raw = await ws.receive_text()
            try:
                req = json.loads(raw)
            except ValueError:
                await ws.send_json({"type": "error", "detail": "invalid json"})
                continue

            try:
                payload = ChatRequest.model_validate(req)
            except Exception as e:
                await ws.send_json({"type": "error", "detail": str(e)})
                continue

            # Open a fresh DB session per message — long-lived sessions
            # hold connections and starve the pool.
            async with SessionFactory() as db:
                session_id = payload.session_id
                if session_id is None:
                    new_session = await SessionRepository(db).create(user_id)
                    await db.commit()
                    session_id = new_session.id

                state = await load_state(db, session_id=session_id, user_id=user_id)
                manager = DialogueManager(db, state)
                result = await manager.handle(payload.message)
                await db.commit()

            # Stream the response text word-by-word so the client sees
            # progress — the DialogueManager already committed; this is
            # purely presentational.
            for chunk in result.text.split(" "):
                await ws.send_json({"type": "token", "content": chunk + " "})

            await ws.send_json(
                {
                    "type": "done",
                    "payload": ChatResponse(
                        session_id=result.state.session_id,
                        turn=result.state.turn,
                        intent=result.intent,
                        intent_confidence=result.intent_confidence,
                        text=result.text,
                        recommendations=_to_cards(result.recommendations),
                    ).model_dump(mode="json"),
                }
            )
    except WebSocketDisconnect:
        log.info("ws_disconnect", user_id=str(user_id))


async def _authenticate_ws(ws: WebSocket, token: str | None) -> uuid.UUID | None:
    """Accept token via ?token=; fall back to the first frame."""
    if token is None:
        try:
            first = await ws.receive_json()
        except Exception:
            return None
        if isinstance(first, dict) and isinstance(first.get("auth"), str):
            token = first["auth"]
    if not token:
        return None
    try:
        claims = decode_token(token)
    except ValueError:
        return None
    if claims.type != "access":
        return None
    async with SessionFactory() as db:
        user = await UserRepository(db).get(uuid.UUID(claims.sub))
    if user is None or not user.is_active:
        return None
    return user.id
