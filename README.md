# Mysterium

**RAG-powered research platform** — upload documents, search with [verity-rag](https://pypi.org/project/verity-rag/), and synthesise structured reports with [pydantic-deep](https://github.com/vstorm-co/pydantic-deepagents) agents.

---

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- A running [verity-rag](https://pypi.org/project/verity-rag/) server (see its docs for setup)
- An [Anthropic API key](https://console.anthropic.com/) (for the research agent)

### Setup

```bash
# Clone and enter the project
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
| `POST` | `/api/research/report` | Generate full research report |
| `POST` | `/api/research/ask` | Quick Q&A from RAG context |

## Configuration

All settings via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_SERVER_URL` | `http://localhost:8100` | verity-rag server address |
| `ANTHROPIC_API_KEY` | — | API key for research agent |
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
- **`create_deep_agent`** — configures the agent with RAG search tools and web search capability
- **Structured output** — the `ResearchReport` Pydantic model is used as `output_type` for type-safe report generation
- **Tool-use** — the agent calls RAG search as a tool, retrieves context, then synthesises the report
- **Subagent delegation** — for complex research, the main agent delegates to specialised subagents (researcher, writer, fact-checker)

## License

MIT
