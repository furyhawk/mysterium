# Mysterium

**RAG-powered research platform** — upload documents, search with [verity-rag](https://pypi.org/project/verity-rag/), and synthesise structured reports with [pydantic-deep](https://github.com/vstorm-co/pydantic-deepagents) agents.

---

## Quick Start

### Option A — Containerised (Docker / Podman Compose) 🐳

### Prerequisites

- [Docker](https://docs.docker.com/engine/install/) or [Podman](https://podman.io/) with Compose plugin
- An [Anthropic API key](https://console.anthropic.com/) (for the research agent)

### Setup

```bash
cd mysterium

# Create environment config
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY
# (RAG_SERVER_URL is automatically set in the compose network)

# Build and start all services
make up-build

# Or if using Podman:
# make up-build DOCKER=podman
```

Open **http://localhost:8200** in your browser.

> The compose stack starts **Mysterium** (FastAPI, :8200), **verity-rag** (RAG server, :8100), **PostgreSQL**, **Valkey** (Redis-compatible), and **Milvus** (vector database). All external services are pre-configured to talk to each other.

### Useful Makefile commands

```bash
make build          # Build container images
make up             # Start all services in detached mode
make logs           # Follow Mysterium logs
make logs service=rag-server   # Follow RAG server logs
make down           # Stop & remove containers (keeps volumes)
make destroy        # Stop & remove everything INCLUDING data volumes
make shell          # Open a shell in the mysterium container
make health         # Check health of both services
make docker-publish # Build and push multi-arch images for linux/amd64 and linux/arm64
make help           # Show all targets
```

### Option B — Local (uv)

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- A running [verity-rag](https://pypi.org/project/verity-rag/) server (see its docs for setup)
- An [Anthropic API key](https://console.anthropic.com/) (for the research agent)

### Setup

```bash
cd mysterium

# Install dependencies
uv sync

# Create your environment config
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and RAG_SERVER_URL

# Run the server
uv run python -m mysterium.main
```

Open **http://localhost:8200** in your browser.

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Browser   │────▶│  Mysterium   │────▶│ verity-rag  │
│   (Vanilla  │     │  (FastAPI)   │     │ (RAG server)│
│    SPA)     │◀────│              │◀────│             │
└─────────────┘     │   +─────────┤     └─────────────┘
                    │   │pydantic- │
                    │   │deep agent│
                    │   │(research)│
                    │   └─────────┘
                    └──────────────┘
```

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Static HTML + CSS + JS (no build step) | Upload, search, research UI |
| **API Gateway** | FastAPI | Proxies document operations to verity-rag; hosts research agent |
| **RAG Engine** | [verity-rag](https://pypi.org/project/verity-rag/) | Document ingestion, chunking, embedding, hybrid search (Milvus + BM25) |
| **Research Agent** | [pydantic-deep](https://github.com/vstorm-co/pydantic-deepagents) | Structured report synthesis from RAG context + LLM analysis |

## Features

### 📤 Upload
- Drag-and-drop file upload (PDF, DOCX, TXT, Markdown)
- Documents sent to verity-rag for parsing → chunking → embedding
- Real-time status tracking per document

### 🔍 Search
- Vector similarity search across document collections
- Optional cross-encoder reranking for improved relevance
- Score-based results with source attribution

### 📊 Research Reports
- Generate structured, cited research reports from your document corpus
- Uses pydantic-deep agents to synthesise RAG results with LLM analysis
- **Web augmentation** — the agent can search & fetch the web (toggleable) to fill gaps in the document store with current public information
- **Live progress feedback** — the UI streams phases as they happen ("Searching your documents…", "Searching the web…", "Fetching a web page…", "Synthesizing the final report…") while the report is generated
- Executive summary, key findings, detailed sections, source citations, and identified knowledge gaps
- Quick Q&A mode for direct questions against your documents

## API Endpoints

### Documents
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/documents/health` | verity-rag health check |
| `GET` | `/api/documents/collections` | List collections |
| `POST` | `/api/documents/collections` | Create collection |
| `DELETE` | `/api/documents/collections/{name}` | Delete collection |
| `POST` | `/api/documents/upload` | Upload document |
| `GET` | `/api/documents` | List documents |
| `GET` | `/api/documents/{id}` | Get document detail |
| `DELETE` | `/api/documents/{id}` | Delete document |
| `POST` | `/api/documents/search` | Search documents |

### Research
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/research/report` | Generate full research report (returns when done) |
| `POST` | `/api/research/report/stream` | Generate research report with live SSE progress phases |
| `POST` | `/api/research/ask` | Quick Q&A from RAG context |

The streaming endpoint (`/api/research/report/stream`) returns a
`text/event-stream` of JSON events:
`{"type": "phase", "message": "...", "tool": "..."}` for each phase the agent
reaches, followed by `{"type": "report", "report": {...}}` with the final
structured report (or `{"type": "error", "message": "..."}` on failure).

## Configuration

All settings via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_SERVER_URL` | `http://localhost:8100` | verity-rag server address |
| `ANTHROPIC_API_KEY` | — | API key for research agent |
| `ANTHROPIC_BASE_URL` | — | Optional custom base URL for an Anthropic-compatible gateway |
| `ANTHROPIC_MAX_TOKENS` | `32768` | Max output tokens for research report generation |
| `RESEARCH_USE_WEB` | `true` | Augment RAG research with web search |
| `RESEARCH_WEB_FETCH` | `auto` | Enable web page fetch. `auto` = on with the official Anthropic API, off when `ANTHROPIC_BASE_URL` is set (most gateways reject the `web_fetch` tool) |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8200` | Server port |
| `LOG_LEVEL` | `info` | Logging level |

## Development

```bash
# Run with auto-reload
uv run uvicorn mysterium.main:app --reload --port 8200

# Or using the module directly
uv run python -m mysterium.main
```

## How It Uses the Libraries

### verity-rag (rag_agent)
The `RAGClient` in `mysterium/clients/rag_client.py` wraps verity-rag's REST API:
- **Document upload** — proxies multipart file uploads to `/api/v1/documents/upload`
- **Vector search** — sends queries to `/api/v1/search` for hybrid (vector + BM25) retrieval
- **Collection management** — creates, lists, and deletes Milvus-backed vector collections
- **Document tracking** — lists, inspects, and deletes ingested documents with status info

The client uses verity-rag's own `schemas` models for type-safe request/response handling.

### pydantic-deep (pydantic_deep)
The research agent in `mysterium/agents/__init__.py` uses pydantic-deep's agent framework:
- **`create_deep_agent`** — drives report generation, wired with custom RAG tools and [web search](https://pydantic.dev/docs/ai/capabilities/web-search/) capability
- **Custom RAG tools** — `rag_search` / `list_collections` are async functions that query verity-rag via `ctx.deps` (a `DeepAgentDeps` subclass carrying the `RAGClient`)
- **Web tools** — [WebSearch](https://pydantic.dev/docs/ai/capabilities/web-search/) + [WebFetch](https://pydantic.dev/docs/ai/capabilities/web-fetch/) are enabled by default so the agent extends private documents with live public sources
- **Structured output** — the `ResearchReport` Pydantic model is set as `output_type`, so the model must produce a validated report (no manual JSON parsing)
- **Headless mode** — filesystem, shell, sub-agents and persistent memory are disabled for the single-shot API task; the model's HTTP client is closed after each run via `async with agent`

## License

MIT
