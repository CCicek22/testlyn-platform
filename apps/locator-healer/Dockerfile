# =============================================================================
# Testlyn Locator Healer — distroless Python
# =============================================================================

FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
RUN uv pip install --system \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "pydantic>=2" \
    "structlog>=25.3" \
    "httpx>=0.28" \
    "redis[asyncio]>=5.0"

COPY main.py ./

FROM gcr.io/distroless/python3-debian12 AS runtime

COPY --from=builder /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=builder /usr/local/bin/python3.13 /usr/local/bin/python3
COPY --from=builder /app /app

WORKDIR /app

EXPOSE 8090

ENV PORT=8090

ENTRYPOINT ["/usr/local/bin/python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
