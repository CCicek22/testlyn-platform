# syntax=docker/dockerfile:1.7
#
# Testlyn API Dockerfile.
# Build context MUST be the repo root (uv workspace member at apps/api).
#   docker build -f apps/api/Dockerfile -t testlyn-api .

FROM python:3.13-slim AS builder

WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Workspace manifests for layer cache
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml

# Install only production deps for the api workspace package
RUN uv sync --frozen --no-dev --no-install-project --package testlyn-api

# Project source
COPY apps/api/testlyn_api/ apps/api/testlyn_api/
COPY apps/api/alembic.ini apps/api/alembic.ini
COPY apps/api/alembic/ apps/api/alembic/

RUN uv sync --frozen --no-dev --package testlyn-api


FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app

COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/apps/api/testlyn_api /app/testlyn_api
COPY --from=builder /build/apps/api/alembic.ini /app/alembic.ini
COPY --from=builder /build/apps/api/alembic /app/alembic

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["/app/.venv/bin/uvicorn", "testlyn_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
