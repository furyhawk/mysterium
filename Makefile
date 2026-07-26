# ── Mysterium — Docker Compose + Python dev helpers ──────────────────
# Podman users: prefix commands with DOCKER=podman (e.g. `make build DOCKER=podman`)
# ────────────────────────────────────────────────────────────────────────────

DOCKER     ?= docker
COMPOSE    ?= $(DOCKER) compose

SERVICE    ?= mysterium

# ── Build & Start ───────────────────────────────────────────────────

## Build all container images
build:
	$(COMPOSE) build

## Build and start all services in detached mode
up:
	$(COMPOSE) up -d

## Build (if needed) and start all services
up-build: build up

## Start a specific service (e.g. `make start service=mysterium`)
start:
	$(COMPOSE) up -d $(SERVICE)

## View logs from a service (e.g. `make logs`, `make logs service=rag-server`)
logs:
	$(COMPOSE) logs -f $(SERVICE)

## List running containers
ps:
	$(COMPOSE) ps

# ── Stop & Clean ────────────────────────────────────────────────────

## Stop all services
stop:
	$(COMPOSE) stop

## Stop and remove containers, networks — keeps volumes
down:
	$(COMPOSE) down

## Stop, remove containers, networks, AND volumes (destroys data!)
destroy:
	$(COMPOSE) down -v

# ── Management ──────────────────────────────────────────────────────

## Pull latest images for external services (postgres, valkey, milvus)
pull:
	$(COMPOSE) pull

## Restart a specific service (e.g. `make restart service=rag-server`)
restart:
	$(COMPOSE) restart $(SERVICE)

## Run a one-off command in the app container
run:
	$(COMPOSE) run --rm $(SERVICE) $(CMD)

## Open a shell in the app container
shell:
	$(COMPOSE) exec $(SERVICE) /bin/bash

# ── Database / Migrations (verity-rag) ─────────────────────────────

## Run Alembic migrations inside the RAG container
migrate:
	$(COMPOSE) exec rag-server alembic upgrade head

## Show migration history
migrate-history:
	$(COMPOSE) exec rag-server alembic history

# ── Verification ────────────────────────────────────────────────────

## Check service health
health:
	@echo "── Mysterium ─────────────────────────────"
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8200/api/documents/health || echo "unhealthy"
	@echo "── verity-rag ───────────────────────────"
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8100/health || echo "unhealthy"

# ── Local dev (without containers) ──────────────────────────────────

## Sync dependencies with uv
uv-sync:
	uv sync

## Run the app locally with uvicorn (requires .env)
dev:
	uv run uvicorn mysterium.main:app --reload --port 8200

# ── Help ────────────────────────────────────────────────────────────

## Show all targets and descriptions
help:
	@printf "\n\033[1mUsage:\033[0m  make \033[36m<target>\033[0m [DOCKER=podman] [SERVICE=name]\n\n"
	@printf "\033[1mTargets:\033[0m\n\n"
	@grep -Eh '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@printf "\n\033[1mVariables:\033[0m\n"
	@printf "  \033[33mDOCKER\033[0m   = $(DOCKER)        (change to podman)\n"
	@printf "  \033[33mSERVICE\033[0m  = $(SERVICE)       (target service name)\n"
	@printf "  \033[33mCMD\033[0m      =                 (command for run target)\n\n"

.PHONY: build up up-build start logs ps stop down destroy pull restart run shell migrate migrate-history health uv-sync dev help
