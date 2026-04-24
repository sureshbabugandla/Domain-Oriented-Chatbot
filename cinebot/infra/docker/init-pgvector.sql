-- Runs once on first Postgres container start. Enables pgvector
-- so migrations can create vector columns + indexes.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- fuzzy text search on titles
CREATE EXTENSION IF NOT EXISTS unaccent;   -- accent-insensitive matching

-- Dedicated schema keeps app tables separate from pg internals.
CREATE SCHEMA IF NOT EXISTS cinebot AUTHORIZATION cinebot;
