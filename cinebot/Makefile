# CineBot — developer ergonomics.
# `make help` prints available targets.

.DEFAULT_GOAL := help
SHELL := /bin/bash
COMPOSE := docker compose
PY := backend/.venv/bin/python

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ── Local dev ────────────────────────────────────────────────
.PHONY: dev
dev: ## Build & start full stack (api, db, redis, mlflow, grafana, frontend)
	$(COMPOSE) up --build -d
	@echo "✓ Stack up. API → http://localhost:8000/docs  UI → http://localhost:5173"

.PHONY: dev-logs
dev-logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=100

.PHONY: down
down: ## Stop stack (keep volumes)
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop stack AND delete volumes (DB reset)
	$(COMPOSE) down -v

.PHONY: ps
ps: ## Show running containers
	$(COMPOSE) ps

# ── Data & ML ────────────────────────────────────────────────
.PHONY: seed
seed: ## Ingest TMDB catalog + generate embeddings
	$(COMPOSE) exec api python -m app.scripts.ingest_tmdb
	$(COMPOSE) exec api python -m app.scripts.build_embeddings

.PHONY: train-intent
train-intent: ## Fine-tune DistilBERT intent classifier
	$(COMPOSE) exec api python -m app.scripts.train_intent

.PHONY: pull-ollama
pull-ollama: ## Pull Llama 3.1 8B into the Ollama container
	$(COMPOSE) exec ollama ollama pull llama3.1:8b

# ── Database ─────────────────────────────────────────────────
.PHONY: migrate
migrate: ## Apply Alembic migrations
	$(COMPOSE) exec api alembic upgrade head

.PHONY: migration
migration: ## Create a new migration; use m="description"
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(m)"

.PHONY: psql
psql: ## Open psql shell
	$(COMPOSE) exec postgres psql -U cinebot -d cinebot

# ── Quality ──────────────────────────────────────────────────
.PHONY: lint
lint: ## Lint backend + frontend
	cd backend && ruff check app tests && black --check app tests && mypy app
	cd frontend && pnpm lint

.PHONY: fmt
fmt: ## Auto-format everything
	cd backend && ruff check --fix app tests && black app tests
	cd frontend && pnpm format

.PHONY: test
test: ## Run backend unit + integration tests
	cd backend && pytest -v --cov=app --cov-report=term-missing --cov-fail-under=80

.PHONY: test-fe
test-fe: ## Run frontend tests
	cd frontend && pnpm test

.PHONY: load-test
load-test: ## Locust load test against local API
	locust -f scripts/locustfile.py --host=http://localhost:8000

# ── Security ─────────────────────────────────────────────────
.PHONY: scan
scan: ## Scan images + deps for CVEs (trivy, pip-audit, npm-audit)
	trivy image cinebot-api:latest || true
	cd backend && pip-audit || true
	cd frontend && pnpm audit || true

# ── Build ────────────────────────────────────────────────────
.PHONY: build
build: ## Build production images
	$(COMPOSE) -f docker-compose.yml -f infra/docker/compose.prod.yml build

# ── Housekeeping ─────────────────────────────────────────────
.PHONY: shell
shell: ## Open bash in API container
	$(COMPOSE) exec api bash
