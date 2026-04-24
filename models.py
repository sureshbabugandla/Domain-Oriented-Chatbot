"""SQLAlchemy 2.0 declarative models.

Schema design notes:

* UUIDs everywhere except the catalog (TMDB has stable int ids).
* Sessions persist across WebSocket disconnects — the client reconnects with
  session_id and resumes slot state.
* Messages store raw user text + classified intent + extracted entities so
  the dialogue manager can replay without re-running NLP.
* `movies.embedding` is a pgvector column indexed with HNSW for sub-ms kNN
  (see migration). Falls back to ivfflat on older pgvector.
* `ratings` captures explicit feedback (thumbs up/down → -1/+1) while
  `movie_impressions` captures implicit (shown-but-ignored vs shown-and-clicked).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import settings


class Base(DeclarativeBase):
    """Shared base — gives every model `id`-less behavior; models declare their own."""

    type_annotation_map = {dict: JSON, list: JSON}


# ── Enums ─────────────────────────────────────────────────
class IntentLabel(StrEnum):
    GREET = "greet"
    RECOMMEND = "recommend"
    REFINE = "refine"
    FEEDBACK = "feedback"
    MORE_INFO = "more_info"
    GOODBYE = "goodbye"
    OOS = "oos"                # out of scope


class FeedbackSignal(StrEnum):
    LIKE = "like"
    DISLIKE = "dislike"
    CLICK = "click"
    DISMISS = "dismiss"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ── Join tables ───────────────────────────────────────────
movie_genres = Table(
    "movie_genres",
    Base.metadata,
    Column(
        "movie_id",
        BigInteger,
        ForeignKey("movies.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "genre_id",
        Integer,
        ForeignKey("genres.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_movie_genres_genre", "genre_id"),
)


# ── Core models ───────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    ratings: Mapped[list[Rating]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    """A multi-turn conversation. Slot state persists across disconnects."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    slots: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_recommendation_ids: Mapped[list] = mapped_column(
        JSON, default=list, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")
    messages: Mapped[list[Message]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    __table_args__ = (
        Index("ix_sessions_user_started", "user_id", "started_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(32))
    intent_confidence: Mapped[float | None] = mapped_column(Float)
    entities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system')", name="ck_message_role"),
        Index("ix_messages_session_created", "session_id", "created_at"),
    )


# ── Catalog ───────────────────────────────────────────────
class Genre(Base):
    __tablename__ = "genres"

    # TMDB genre IDs are stable — keep them
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class Movie(Base):
    __tablename__ = "movies"

    # TMDB id is the primary key for deterministic upserts.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    original_title: Mapped[str | None] = mapped_column(String(512))
    overview: Mapped[str | None] = mapped_column(Text)
    tagline: Mapped[str | None] = mapped_column(String(512))
    release_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=False))
    runtime_minutes: Mapped[int | None] = mapped_column(Integer)
    original_language: Mapped[str | None] = mapped_column(String(8))
    popularity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    vote_average: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    poster_path: Mapped[str | None] = mapped_column(String(256))
    backdrop_path: Mapped[str | None] = mapped_column(String(256))
    adult: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Derived: overview + genres + keywords concatenated, then embedded.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimension)
    )
    embedding_updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    genres: Mapped[list[Genre]] = relationship(secondary=movie_genres, lazy="selectin")
    ratings: Mapped[list[Rating]] = relationship(
        back_populates="movie", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Popularity-based ranking
        Index("ix_movies_popularity_desc", popularity.desc()),
        Index("ix_movies_vote_average_desc", vote_average.desc()),
        Index("ix_movies_release_date", "release_date"),
        # Fuzzy title search via pg_trgm
        Index(
            "ix_movies_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        # HNSW for cosine kNN — created in a migration rather than here
        # because HNSW params aren't well-supported by the SQLA DDL generator.
    )


class Rating(Base):
    """Explicit feedback: user thumbed up/down a specific recommendation."""

    __tablename__ = "ratings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    movie_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("movies.id", ondelete="CASCADE"),
        nullable=False,
    )
    # -1 dislike, 0 neutral/clicked, +1 like
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="ratings")
    movie: Mapped[Movie] = relationship(back_populates="ratings")

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_rating_user_movie"),
        CheckConstraint("value IN (-1, 0, 1)", name="ck_rating_value"),
        Index("ix_ratings_user_movie", "user_id", "movie_id"),
    )


class MovieImpression(Base):
    """Implicit feedback: recommendation shown to user (clicked or not)."""

    __tablename__ = "movie_impressions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    movie_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("movies.id", ondelete="CASCADE"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    signal: Mapped[str | None] = mapped_column(String(16))
    score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_impressions_session", "session_id"),
        Index("ix_impressions_movie", "movie_id"),
    )
