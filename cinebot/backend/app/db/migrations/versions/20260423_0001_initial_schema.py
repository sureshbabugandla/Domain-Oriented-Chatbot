"""initial schema with pgvector

Revision ID: 20260423_0001
Revises:
Create Date: 2026-04-23 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "20260423_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extensions — init-pgvector.sql runs these on DB creation, but
    # idempotent CREATEs keep fresh environments (CI, tests) working.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # ── users ───────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255)),
        sa.Column("display_name", sa.String(120)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("preferences", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── sessions ────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slots", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "last_recommendation_ids",
            postgresql.JSON,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index(
        "ix_sessions_user_started", "sessions", ["user_id", "started_at"]
    )

    # ── messages ────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("intent", sa.String(32)),
        sa.Column("intent_confidence", sa.Float),
        sa.Column("entities", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "role IN ('user','assistant','system')", name="ck_message_role"
        ),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index(
        "ix_messages_session_created", "messages", ["session_id", "created_at"]
    )

    # ── genres ──────────────────────────────────────────
    op.create_table(
        "genres",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
    )

    # ── movies ──────────────────────────────────────────
    op.create_table(
        "movies",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("original_title", sa.String(512)),
        sa.Column("overview", sa.Text),
        sa.Column("tagline", sa.String(512)),
        sa.Column("release_date", sa.TIMESTAMP(timezone=False)),
        sa.Column("runtime_minutes", sa.Integer),
        sa.Column("original_language", sa.String(8)),
        sa.Column("popularity", sa.Float, nullable=False, server_default="0"),
        sa.Column("vote_average", sa.Float, nullable=False, server_default="0"),
        sa.Column("vote_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("poster_path", sa.String(256)),
        sa.Column("backdrop_path", sa.String(256)),
        sa.Column("adult", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("embedding", Vector(384)),
        sa.Column("embedding_updated_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_movies_title", "movies", ["title"])
    op.create_index(
        "ix_movies_popularity_desc", "movies", [sa.text("popularity DESC")]
    )
    op.create_index(
        "ix_movies_vote_average_desc", "movies", [sa.text("vote_average DESC")]
    )
    op.create_index("ix_movies_release_date", "movies", ["release_date"])

    # Fuzzy title search (pg_trgm)
    op.execute(
        "CREATE INDEX ix_movies_title_trgm ON movies USING gin (title gin_trgm_ops)"
    )

    # HNSW index for cosine kNN — far faster than ivfflat for read-heavy
    # workloads and doesn't need a LISTS tuning. m=16, ef_construction=64
    # are pgvector defaults; bump ef_search at query time if recall matters.
    op.execute(
        "CREATE INDEX ix_movies_embedding_hnsw ON movies "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # ── movie_genres (M2M) ──────────────────────────────
    op.create_table(
        "movie_genres",
        sa.Column(
            "movie_id",
            sa.BigInteger,
            sa.ForeignKey("movies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "genre_id",
            sa.Integer,
            sa.ForeignKey("genres.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index("ix_movie_genres_genre", "movie_genres", ["genre_id"])

    # ── ratings ─────────────────────────────────────────
    op.create_table(
        "ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "movie_id",
            sa.BigInteger,
            sa.ForeignKey("movies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.Integer, nullable=False),
        sa.Column(
            "source_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "movie_id", name="uq_rating_user_movie"),
        sa.CheckConstraint("value IN (-1, 0, 1)", name="ck_rating_value"),
    )
    op.create_index("ix_ratings_user_movie", "ratings", ["user_id", "movie_id"])

    # ── movie_impressions ───────────────────────────────
    op.create_table(
        "movie_impressions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "movie_id",
            sa.BigInteger,
            sa.ForeignKey("movies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("signal", sa.String(16)),
        sa.Column("score", sa.Float),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_impressions_session", "movie_impressions", ["session_id"])
    op.create_index("ix_impressions_movie", "movie_impressions", ["movie_id"])


def downgrade() -> None:
    op.drop_table("movie_impressions")
    op.drop_table("ratings")
    op.drop_table("movie_genres")
    op.execute("DROP INDEX IF EXISTS ix_movies_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_movies_title_trgm")
    op.drop_table("movies")
    op.drop_table("genres")
    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("users")
