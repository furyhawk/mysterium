# ── Build stage ─────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-dev

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

USER mysterium

EXPOSE 8200

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import http.client; c = http.client.HTTPConnection('localhost', 8200); c.request('GET', '/api/documents/health'); assert c.getresponse().status == 200" 2>/dev/null || exit 1

CMD ["uvicorn", "mysterium.main:app", "--host", "0.0.0.0", "--port", "8200"]
