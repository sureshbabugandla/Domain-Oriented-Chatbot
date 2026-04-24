# 🎬 CineBot — Conversational Movie Recommender

A production-grade, domain-oriented chatbot that recommends movies via natural-language
conversation. Built with FastAPI, spaCy, DistilBERT, Sentence-Transformers,
pgvector, Redis, Celery, React + TypeScript, and a toggleable LLM backend
(OpenAI GPT-4o-mini or local Llama 3.1 via Ollama).

```
"I'm feeling sad, something feel-good from the 90s?"
  → intent=recommend  mood=sad  era=1990s  preference=uplifting
  → top-5 ranked, explained, streamed over WebSocket
```

## Quickstart

```bash
cp .env.example .env           # fill in TMDB_API_KEY (and OPENAI_API_KEY if using)
make dev                        # docker compose up --build
make seed                       # ingest TMDB catalog + build embeddings
open http://localhost:5173      # React chat UI
```

Services on `make dev`:

| Service       | URL                          | Purpose                        |
|---------------|------------------------------|--------------------------------|
| Frontend      | http://localhost:5173        | React + Vite chat UI           |
| API           | http://localhost:8000/docs   | FastAPI + OpenAPI              |
| Postgres      | localhost:5432               | pgvector-enabled catalog + DB  |
| Redis         | localhost:6379               | Sessions, cache, rate-limit    |
| MLflow        | http://localhost:5000        | Experiment + model registry    |
| Prometheus    | http://localhost:9090        | Metrics                        |
| Grafana       | http://localhost:3001        | Dashboards (admin/admin)       |
| Ollama        | http://localhost:11434       | Local LLM (optional)           |

## Repository Layout

```
cinebot/
├── backend/                       FastAPI app
│   ├── app/
│   │   ├── api/                   Routes, schemas, middleware (auth/log/rate-limit)
│   │   ├── core/                  Config, logging, security, LLM, Redis, metrics
│   │   ├── db/                    SQLAlchemy models, repos, Alembic migrations
│   │   ├── dialogue/              State, policy/orchestrator, response templates
│   │   ├── nlp/                   Preprocessor, embedder, NER, intent classifier, pipeline
│   │   ├── recommender/           Hybrid retrieval, MMR ranker, explainer
│   │   ├── scripts/               TMDB ingest, embedding backfill, intent training
│   │   ├── workers/               Celery app + tasks
│   │   └── main.py                App assembly — lifespan, middleware, routers
│   ├── tests/                     pytest unit + integration suites
│   ├── Dockerfile                 3-stage: builder → dev → prod (non-root, healthcheck)
│   ├── alembic.ini
│   └── pyproject.toml
├── frontend/                      Vite + React 18 + TS + Tailwind + shadcn/Radix
│   ├── src/
│   │   ├── components/            MessageList, RecommendationCard, ChatComposer, Sidebar, Sprocket
│   │   ├── pages/                 ChatPage, AuthPage
│   │   ├── hooks/                 useChatSocket (WS + reconnect)
│   │   ├── lib/                   API client, Zustand store, utils
│   │   ├── styles/                Tailwind base + cinematic theme tokens
│   │   ├── types/                 Wire-format types (mirror of backend schemas)
│   │   ├── App.tsx / main.tsx
│   │   └── test-setup.ts
│   ├── Dockerfile                 Dev (HMR) + prod (nginx) stages
│   ├── nginx.conf                 SPA routing + REST/WS proxy to api
│   └── package.json
├── ml/
│   └── data/intents_sample.jsonl  Seed intent training data (7 classes, ~210 examples)
├── infra/
│   ├── docker/init-pgvector.sql   Enables vector + pg_trgm + unaccent on DB creation
│   ├── prometheus/prometheus.yml
│   └── grafana/
│       ├── datasources/           Auto-provisioned Prometheus datasource
│       └── dashboards/            JSON dashboards + provisioning config
├── scripts/
│   ├── locustfile.py              Load test (50+ users, p95 < 2s target)
│   └── cinebot.postman_collection.json
├── docs/
│   ├── ARCHITECTURE.md            High-level + sequence diagrams (Mermaid)
│   ├── RUNBOOK.md                 Deploy, rollback, 8 common incidents
│   └── EVALUATION.md              Intent F1, NDCG@5, latency report template
├── .github/workflows/ci.yml       lint → test → build → Trivy scan
├── docker-compose.yml             One-command local stack (9 services)
├── Makefile                       make dev / seed / test / lint / migrate / scan
├── .env.example
├── .pre-commit-config.yaml        ruff + black + mypy + eslint + detect-secrets
└── README.md
```

See `docs/ARCHITECTURE.md` for diagrams and `docs/RUNBOOK.md` for operations.
