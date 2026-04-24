# CineBot — architecture

## High-level

```mermaid
flowchart TB
  User([User]) -->|HTTPS + WSS| SPA[React SPA<br/>Vite · Tailwind · shadcn/ui]
  SPA -->|REST + WS| API{{FastAPI pods}}

  subgraph App["Application layer"]
    Auth[Auth service<br/>JWT · rate limits]
    Chat[Chat orchestrator<br/>Dialogue state · policy]
    Fb[Feedback service<br/>Likes · ratings]
    NLP[NLP pipeline<br/>Intent · NER · embed]
    Rec[Recommender<br/>Hybrid · rerank · explain]
    Sess[Session manager<br/>Redis-backed state]
  end

  API --> Auth & Chat & Fb
  Chat --> NLP & Rec & Sess

  NLP --> Postgres[(Postgres 16)]
  Rec --> PGV[(pgvector index)]
  Sess --> Redis[(Redis 7)]

  Rec --> LLM[LLM backend<br/>OpenAI or Ollama]
  Redis --> Celery[Celery workers<br/>Embeddings · feedback]
  Postgres --> TMDB[TMDB API<br/>Catalog ingestion]
```

## Chat turn — sequence

```mermaid
sequenceDiagram
  participant C as Client
  participant A as API
  participant S as Session
  participant N as NLP
  participant R as Recommender
  participant L as LLM

  C->>A: 1. WS send message
  A->>S: 2. Load state
  S-->>A: 3. History + slots
  A->>N: 4. Classify + extract
  N-->>A: 5. Intent + entities + embedding
  A->>S: 6. Merge slots
  A->>R: 7. Get candidates
  R-->>A: 8. Top-K with scores
  A->>L: 9. Generate explanations
  L-->>A: 10. Stream tokens
  A-->>C: 11. Forward stream
  A->>S: 12. Persist turn (async via Celery)
  C->>A: 13. POST feedback
  A->>S: 14. Update prefs
```

## Notes

- NLP runs in-process (no network hop between API and NLP pipeline).
- Step 9 is wrapped in tenacity retry + circuit breaker; provider toggle via `LLM_PROVIDER` env.
- Step 12 is non-blocking — the response to the user does not wait on persistence.
- Embedding generation during ingestion is batched through a Celery worker, not the hot path.
