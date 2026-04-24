# CineBot Runbook

> On-call reference. If it's 3am and something is broken, the answer is (probably) in here.

## Table of contents

- [First response checklist](#first-response-checklist)
- [Deployment](#deployment)
- [Rollback](#rollback)
- [Common incidents](#common-incidents)
- [Observability quick reference](#observability-quick-reference)

---

## First response checklist

1. Open Grafana → **CineBot — Service Overview** at http://localhost:3001
2. Check the four stat panels at the top:
   - **Requests / sec** — is traffic normal, dead, or spiking?
   - **p95 latency (chat turn)** — over 2s is our SLO breach
   - **5xx rate** — yellow over 0.5%, red over 2%
   - **Recommendations served** — flat line with non-zero traffic means the recommender is failing silently
3. Check **LLM latency + error rate** panel — a dead LLM is the single most common cause of chat-turn latency spikes
4. Check **Feedback → Like ratio** — a drop below 0.6 over 1h usually means something regressed in ranking

If logs are needed, `make dev-logs` tails everything; filter with `docker compose logs api | grep level=error`.

---

## Deployment

### Local / staging (Docker Compose)

```bash
# from a clean checkout
cp .env.example .env           # fill in TMDB_API_KEY (and OPENAI_API_KEY if using OpenAI)
make dev                        # build + start the stack
make migrate                    # apply schema
make seed                       # TMDB catalog + embeddings (~5 min)
make pull-ollama                # optional: download Llama 3.1 (~4GB)
```

Verify:

```bash
curl http://localhost:8000/health                   # → {"status":"ok"}
curl http://localhost:8000/ready                    # → {"status":"ready"} (depends on DB + Redis)
curl http://localhost:8000/metrics | head -5        # Prometheus exposition
open http://localhost:5173                          # SPA loads, auth page visible
```

### Production (future)

The repo ships Docker Compose only as per the scoping decision. The multi-stage Dockerfiles (`backend/Dockerfile` target `prod`, `frontend/Dockerfile` target `prod`) are production-ready: non-root user, healthchecks, gunicorn with uvicorn workers for the API, nginx for the frontend. A future AWS/GCP/k8s deployment should:

1. Promote the `prod` image targets through a container registry
2. Externalize secrets to the cloud secret manager
3. Move `docker-compose.yml` volumes to managed equivalents (RDS for Postgres, ElastiCache for Redis, S3 for MLflow artifacts)
4. Run `alembic upgrade head` as a pre-deploy hook

---

## Rollback

With Docker Compose, rollback means "deploy a previous image tag". The images are built locally by default; for a multi-environment setup:

```bash
# Tag your production release before each deploy
docker tag cinebot-api:latest cinebot-api:v0.1.3
docker push <registry>/cinebot-api:v0.1.3

# To roll back:
docker compose pull        # fetch previous tag (via .env override of IMAGE_TAG)
docker compose up -d api   # recreate only the API container
```

### Database rollback

Alembic ships `downgrade -1` for each migration. **Test in staging first — downgrades that drop columns destroy data.** Preferred strategy for incident recovery is roll forward (write a new migration that restores the broken state), not downgrade.

```bash
# Forward migration (safe)
make migration m="fix ranking weights"
make migrate

# Downgrade (data-destructive; only for pre-release branches)
make shell
alembic downgrade -1
```

### Vector-index rebuild

If the HNSW index gets corrupted or embedding dimensions change:

```bash
make shell
psql -c "DROP INDEX ix_movies_embedding_hnsw"
psql -c "CREATE INDEX ix_movies_embedding_hnsw ON movies USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
# Rebuild takes minutes per 100k rows.
```

---

## Common incidents

### 1. p95 chat latency > 2s

**Likely cause:** LLM provider slow or down.

**Check:**
```
Grafana → LLM latency + error rate panel
docker compose logs api | grep llm_retry
```

**Fix:**
- If using OpenAI: check https://status.openai.com
- If using Ollama: `docker compose restart ollama` and confirm `ollama list` shows the model
- **Workaround:** flip `LLM_PROVIDER` in `.env` to the other backend and `docker compose up -d api`
- Confirm the circuit breaker is kicking in — `api` logs should show `llm_retry` warnings, not long hangs

### 2. "rate limit exceeded" on every request

**Cause:** Redis lost state (restarted, evicted the token-bucket hash) OR a bug set a very low rate.

**Check:** `docker compose exec redis redis-cli --scan --pattern 'rl:*' | head`

**Fix:**
```bash
docker compose exec redis redis-cli FLUSHDB      # clears rate-limit buckets (does not clear sessions — those live in DB)
```

If it keeps happening, look at `RATE_LIMIT_PER_MINUTE` in `.env`.

### 3. Recommendations come back empty

**Cause:** Movies exist but embeddings missing (ingest ran but embedder crashed), or the query embedding isn't being computed.

**Check:**
```bash
make psql
SELECT COUNT(*) FROM movies WHERE embedding IS NULL;
```

**Fix:**
```bash
make shell
python -m app.scripts.build_embeddings
```

Or trigger the Celery task: `celery -A app.workers.celery_app call app.workers.tasks.embed_missing_movies`.

### 4. Intent classification acting odd (everything → `oos`)

The DistilBERT model may not be present — the system falls back to the rule-based classifier, which caps confidence at 0.75 (below our default 0.60 threshold — so it usually works, but edge cases fail).

**Check:** look for `intent_using kind=rule_based` in startup logs. If yes, you're on the fallback.

**Fix:** `make train-intent` (takes ~5 min on CPU with the 210-example seed set; add more labels in `ml/data/intents_sample.jsonl` for better F1).

### 5. WebSocket chat shows "disconnected" but API is up

**Cause:** Usually stale browser tab after backend restart. The hook reconnects with exponential backoff up to 30s, gives up after 6 tries.

**Fix:** Reload the page. If it persists, check `docker compose logs api | grep ws_disconnect`.

### 6. Alembic migration fails on startup

**Cause:** Schema drift between your local DB and the migration file.

**Check:** `alembic current` to see what rev the DB is at.

**Fix:** For *dev only* — `make clean` wipes the DB, `make dev && make migrate` rebuilds from scratch. In staging/prod never do this: file a remediation migration.

### 7. Feedback endpoint returns 202 but nothing persists

**Cause:** Celery worker down. The feedback route enqueues — it doesn't write directly.

**Check:** `docker compose ps celery-worker` — should be running. `docker compose logs celery-worker | tail -20`.

**Fix:** `docker compose restart celery-worker`. Redis retains the queue, so no messages are lost.

### 8. Ingest script rate-limits against TMDB

**Symptom:** `page_failed status=429` in ingest logs.

**Cause:** Too many concurrent requests. The client caps at 10 in-flight (`asyncio.Semaphore(10)`), which is well under TMDB's 40/10s budget — so rate limiting usually means you're re-running ingest faster than the exponential backoff recovers.

**Fix:** Wait 30s, re-run `make seed`. Alternatively, lower `TMDB_INGEST_PAGES` for dev.

---

## Observability quick reference

| Where | What's there |
| --- | --- |
| http://localhost:3001 | Grafana (admin/admin) — start here |
| http://localhost:9090 | Prometheus — ad-hoc PromQL |
| http://localhost:5000 | MLflow — intent classifier training runs |
| `docker compose logs <svc>` | Structured JSON (prod) or colored (dev) logs; filter with `grep level=error` |
| `x-request-id` header | Propagated through every log line; the thread to pull on |

### Useful PromQL snippets

```promql
# Turn p50/p95/p99 in one query
histogram_quantile(0.95, sum by (le) (rate(cinebot_recommendation_latency_seconds_bucket[5m])))

# Which endpoint is slowest?
topk(5, histogram_quantile(0.95, sum by (path, le) (rate(cinebot_http_request_duration_seconds_bucket[5m]))))

# Per-intent rec rate
sum by (intent) (rate(cinebot_recommendations_served_total[5m]))

# LLM failure rate
sum by (provider) (rate(cinebot_llm_requests_total{outcome="failure"}[5m]))
  / sum by (provider) (rate(cinebot_llm_requests_total[5m]))
```
