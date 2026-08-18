# ── Frontend build stage ────────────────────────────────────────────
FROM node:22-alpine AS frontend

WORKDIR /app

# Install dependencies first for better layer caching
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

COPY frontend/ ./frontend/

# Builds the SPA into /app/mysterium/static (FastAPI serves it at /ui)
RUN cd frontend && npm run build

# ── Build stage ─────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml ./
RUN python -c "import subprocess, tomllib; deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; subprocess.check_call(['pip', 'install', '--no-cache-dir', *deps])"

# ── Runtime stage ──────────────────────────────────────────────────
FROM python:3.13-slim

RUN groupadd --system --gid 1001 mysterium && \
    useradd --system --uid 1001 --gid mysterium --no-create-home mysterium && \
    mkdir -p /data && chown -R mysterium:mysterium /data

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY main.py ./
COPY mysterium/ ./mysterium/

# Overwrite any checked-in static assets with the freshly built frontend bundle
COPY --from=frontend /app/mysterium/static ./mysterium/static/

USER mysterium

EXPOSE 8200

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import http.client; c = http.client.HTTPConnection('localhost', 8200); c.request('GET', '/api/documents/health'); assert c.getresponse().status == 200" 2>/dev/null || exit 1

CMD ["uvicorn", "mysterium.main:app", "--host", "0.0.0.0", "--port", "8200"]
