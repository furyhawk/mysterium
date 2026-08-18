# ── Mysterium — Docker Compose + Python dev helpers ──────────────────
# Podman users: prefix commands with DOCKER=podman (e.g. `make build DOCKER=podman`)
# ────────────────────────────────────────────────────────────────────────────

DOCKER     ?= docker
COMPOSE    ?= $(DOCKER) compose
PYTHON     ?= python3
REGISTRY   ?= docker.io
IMAGE      ?= furyhawk/mysterium
VERSION    ?= $(shell $(PYTHON) -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')

SERVICE    ?= mysterium

# ── Build & Start ───────────────────────────────────────────────────

## Build all container images
build:
	$(COMPOSE) build

## Build the mysterium image for the current host architecture with auto tags ($(REGISTRY)/$(IMAGE):latest + $(REGISTRY)/$(IMAGE):$(VERSION))
docker-build:
	$(DOCKER) build \
		-t $(REGISTRY)/$(IMAGE):latest \
		-t $(REGISTRY)/$(IMAGE):$(VERSION) \
		.

## Log in to the container registry (run this before docker-push or docker-publish)
docker-login:
	$(DOCKER) login $(REGISTRY)

## Push the latest and version-tagged images to the registry (run `make docker-login` first)
docker-push:
	$(DOCKER) push $(REGISTRY)/$(IMAGE):$(VERSION)
	$(DOCKER) push $(REGISTRY)/$(IMAGE):latest

## Build and publish the current version image for linux/amd64 and linux/arm64 (run `make docker-login` first)
PLATFORMS ?= linux/amd64,linux/arm64
# Podman uses `build --manifest` + `manifest push`; Docker uses `buildx build --push`
ifeq ($(DOCKER),podman)
# `podman build --manifest` + `manifest push --all` fail with "image is not a
# manifest list" if the target names are already taken by single-arch images
# (e.g. from a prior `make docker-build`). Clear any stale refs first so the
# build registers a fresh manifest list under the version tag.
docker-publish:
	-$(DOCKER) rmi -f $(REGISTRY)/$(IMAGE):$(VERSION) 2>/dev/null || true
	-$(DOCKER) rmi -f $(REGISTRY)/$(IMAGE):latest 2>/dev/null || true
	-$(DOCKER) manifest rm $(REGISTRY)/$(IMAGE):$(VERSION) 2>/dev/null || true
	-$(DOCKER) manifest rm $(REGISTRY)/$(IMAGE):latest 2>/dev/null || true
	$(DOCKER) build \
		--platform $(PLATFORMS) \
		--manifest $(REGISTRY)/$(IMAGE):$(VERSION) \
		.
	$(DOCKER) manifest push --all $(REGISTRY)/$(IMAGE):$(VERSION)
	$(DOCKER) manifest push --all $(REGISTRY)/$(IMAGE):$(VERSION) \
		$(REGISTRY)/$(IMAGE):latest
else
docker-publish:
	$(DOCKER) buildx build \
		--platform $(PLATFORMS) \
		--push \
		-t $(REGISTRY)/$(IMAGE):latest \
		-t $(REGISTRY)/$(IMAGE):$(VERSION) \
		.
endif

## Build and start all services in detached mode
up:
	$(COMPOSE) up -d

## Build (if needed) and start all services
up-build: build up

## Start a specific service (e.g. `make start service=rag-server`)
start:
	$(COMPOSE) up -d $(SERVICE)

## Start only the mysterium service (no dependencies)
start-mysterium:
	$(COMPOSE) up -d mysterium

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
	uv run uvicorn mysterium.main:app --reload --port 8200 --host 0.0.0.0

## Run the app as a background service (logs to mysterium.log)
service:
	nohup uv run uvicorn mysterium.main:app --reload --port 8200 --host 0.0.0.0 > mysterium.log 2>&1 &

## Stop the background service
kill-service:
	@pkill -f "uvicorn mysterium.main:app" && echo "Service stopped" || echo "No service running"

# ── Frontend (Svelte + Vite) ────────────────────────────────────────

## Install frontend dependencies (requires Node/npm)
ui-install:
	cd frontend && npm install

## Build the frontend bundle into mysterium/static (requires Node/npm)
ui-build:
	cd frontend && npm run build

## Run the frontend dev server with HMR (proxies /api to localhost:8200)
ui-dev:
	cd frontend && npm run dev

## Type-check the frontend
ui-check:
	cd frontend && npm run check

## Run frontend unit tests
ui-test:
	cd frontend && npm test

# ── Help ────────────────────────────────────────────────────────────

## Show all targets and descriptions
help:
	@printf "\n\033[1mUsage:\033[0m  make \033[36m<target>\033[0m [DOCKER=podman] [SERVICE=name]\n\n"
	@printf "\033[1mTargets:\033[0m\n\n"
	@grep -Eh '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@printf "\n\033[1mVariables:\033[0m\n"
	@printf "  \033[33mDOCKER\033[0m    = $(DOCKER)        (change to podman)\n"
	@printf "  \033[33mREGISTRY\033[0m  = $(REGISTRY)  (target container registry)\n"
	@printf "  \033[33mSERVICE\033[0m   = $(SERVICE)       (target service name)\n"
	@printf "  \033[33mCMD\033[0m       =                 (command for run target)\n\n"

.PHONY: build docker-build docker-login docker-push docker-publish up up-build start logs ps stop down destroy pull restart run shell migrate migrate-history health uv-sync dev service kill-service help
